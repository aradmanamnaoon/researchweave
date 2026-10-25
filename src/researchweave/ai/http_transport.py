"""DNS-pinned, proxy-independent HTTP POST transport for AI providers.

The resolver returns candidate IPs once. The transport validates *every*
candidate and connects to an explicitly chosen IP while TLS validates the
original hostname and SNI. This avoids hostname checks followed by a second
uncontrolled DNS lookup, as well as environment proxy bypasses.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urlsplit

from .errors import AIError
from .policy import validate_endpoint


class Resolver(Protocol):
    def resolve(self, hostname: str, port: int) -> list[str]: ...


class SocketResolver:
    def resolve(self, hostname: str, port: int) -> list[str]:
        try:
            records = socket.getaddrinfo(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except OSError as exc:
            raise AIError("PROVIDER_UNAVAILABLE", "Provider DNS resolution failed") from exc
        return list(dict.fromkeys(str(record[4][0]) for record in records))


class HTTPReply(Protocol):
    status: int

    def read(self, size: int) -> bytes: ...


class HTTPConnection(Protocol):
    def request(
        self,
        method: str,
        url: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> None: ...

    def getresponse(self) -> HTTPReply: ...

    def close(self) -> None: ...


class ConnectionFactory(Protocol):
    def create(
        self,
        hostname: str,
        pinned_ip: str,
        port: int,
        *,
        tls: bool,
        timeout: float,
    ) -> HTTPConnection: ...


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, hostname: str, pinned_ip: str, port: int, timeout: float) -> None:
        super().__init__(hostname, port=port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        # This socket connection uses an already resolved and validated IP.
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, pinned_ip: str, port: int, timeout: float) -> None:
        context = ssl.create_default_context()
        super().__init__(hostname, port=port, timeout=timeout, context=context)
        self._pinned_ip = pinned_ip
        self._tls_context = context

    def connect(self) -> None:
        # Preserve server hostname for TLS SNI and certificate hostname checks.
        # No environment proxies or HTTP CONNECT tunnels are honored.
        original = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        try:
            self.sock = self._tls_context.wrap_socket(original, server_hostname=self.host)
        except Exception:
            original.close()
            raise


class DirectConnectionFactory:
    def create(
        self,
        hostname: str,
        pinned_ip: str,
        port: int,
        *,
        tls: bool,
        timeout: float,
    ) -> HTTPConnection:
        if tls:
            return _PinnedHTTPSConnection(hostname, pinned_ip, port, timeout)
        return _PinnedHTTPConnection(hostname, pinned_ip, port, timeout)


class PinnedHTTPTransport:
    """Refuses redirects, private DNS resolutions and unbounded responses."""

    def __init__(
        self,
        resolver: Resolver | None = None,
        factory: ConnectionFactory | None = None,
        *,
        max_response_bytes: int = 2_000_000,
        max_request_bytes: int = 2_000_000,
    ) -> None:
        if not 1 <= max_response_bytes <= 20_000_000:
            raise AIError("INVALID_INPUT", "Invalid provider response budget")
        if not 1 <= max_request_bytes <= 20_000_000:
            raise AIError("INVALID_INPUT", "Invalid provider request budget")
        self.resolver = resolver or SocketResolver()
        self.factory = factory or DirectConnectionFactory()
        self.max_response_bytes = max_response_bytes
        self.max_request_bytes = max_request_bytes

    @staticmethod
    def _retry_after(response: HTTPReply) -> float | None:
        getter = getattr(response, "getheader", None)
        raw = getter("Retry-After") if callable(getter) else None
        if raw is not None and not isinstance(raw, str):
            return None
        if raw is None:
            return None
        value = raw.strip()
        if not value:
            return None
        try:
            seconds = float(value)
        except ValueError:
            try:
                target = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
            if target.tzinfo is None:
                target = target.replace(tzinfo=UTC)
            seconds = (target.astimezone(UTC) - datetime.now(UTC)).total_seconds()
        if seconds < 0:
            return 0.0
        return min(seconds, 86_400.0)

    @staticmethod
    def _address_set(hostname: str, addresses: list[str], local: bool) -> str:
        if not addresses or len(addresses) > 32:
            raise AIError("PROVIDER_UNAVAILABLE", "Provider DNS response is missing or excessive")
        normalized: list[str] = []
        for literal in addresses:
            try:
                address = ipaddress.ip_address(literal)
            except ValueError as exc:
                raise AIError("PERMISSION_DENIED", "DNS returned malformed address") from exc
            if local and not address.is_loopback:
                raise AIError("PERMISSION_DENIED", "Local runtime DNS escaped loopback")
            if not local and not address.is_global:
                raise AIError("PERMISSION_DENIED", "DNS returned private or reserved address")
            normalized.append(str(address))
        # Sort for reproducibility. Each candidate was validated before use.
        return sorted(set(normalized))[0]

    def send(self, url: str, headers: Mapping[str, str], payload: bytes, timeout: float) -> bytes:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        if hostname is None:
            raise AIError("INVALID_INPUT", "Provider hostname missing")
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            literal = None
        local = (
            parsed.scheme == "http"
            or hostname.lower()
            in {
                "localhost",
                "localhost.localdomain",
            }
            or bool(literal and literal.is_loopback)
        )
        validate_endpoint(url, local=local)
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise AIError("INVALID_INPUT", "Provider port is malformed") from exc
        if not 1 <= port <= 65535:
            raise AIError("INVALID_INPUT", "Provider port is out of range")
        if not 0.1 <= timeout <= 120:
            raise AIError("INVALID_INPUT", "Provider timeout is out of range")
        if not isinstance(payload, bytes) or len(payload) > self.max_request_bytes:
            raise AIError("RESOURCE_LIMIT", "Provider request exceeds byte budget")
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or "\r" in key + value
            or "\n" in key + value
            for key, value in headers.items()
        ):
            raise AIError("INVALID_INPUT", "Invalid provider request header")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        if len(path) > 8192 or any(ord(c) < 32 for c in path):
            raise AIError("INVALID_INPUT", "Provider path contains invalid characters")
        candidates = self.resolver.resolve(hostname, port)
        pinned_ip = self._address_set(hostname, candidates, local)
        connection: HTTPConnection | None = None
        try:
            connection = self.factory.create(
                hostname, pinned_ip, port, tls=parsed.scheme == "https", timeout=timeout
            )
            connection.request("POST", path, body=payload, headers=headers)
            response = connection.getresponse()
            status = response.status
            if 300 <= status < 400:
                raise AIError("PERMISSION_DENIED", "HTTP redirect blocked")
            if status in {401, 403}:
                raise AIError("PERMISSION_DENIED", f"Provider HTTP {status}")
            if status == 429:
                raise AIError(
                    "RATE_LIMITED",
                    "Provider rate limit reached",
                    retry_after_seconds=self._retry_after(response),
                )
            if status == 503:
                raise AIError(
                    "SERVICE_UNAVAILABLE",
                    "Provider service unavailable",
                    retry_after_seconds=self._retry_after(response),
                )
            if not 200 <= status < 300:
                raise AIError("PROVIDER_UNAVAILABLE", f"Provider HTTP {status}")
            contents = response.read(self.max_response_bytes + 1)
            if len(contents) > self.max_response_bytes:
                raise AIError("RESOURCE_LIMIT", "Provider response exceeds byte budget")
            return bytes(contents)
        except AIError:
            raise
        except (OSError, TimeoutError, http.client.HTTPException, ssl.SSLError) as exc:
            raise AIError("PROVIDER_UNAVAILABLE", "Provider connection failed") from exc
        finally:
            if connection is not None:
                connection.close()

    def stream(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: bytes,
        timeout: float,
        *,
        chunk_size: int = 8192,
    ) -> Iterator[bytes]:
        """Yield bounded response bytes while preserving the same pinned-network policy as send."""

        if not 1 <= chunk_size <= 262_144:
            raise AIError("INVALID_INPUT", "Invalid provider stream chunk size")
        parsed = urlsplit(url)
        hostname = parsed.hostname
        if hostname is None:
            raise AIError("INVALID_INPUT", "Provider hostname missing")
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            literal = None
        local = (
            parsed.scheme == "http"
            or hostname.lower() in {"localhost", "localhost.localdomain"}
            or bool(literal and literal.is_loopback)
        )
        validate_endpoint(url, local=local)
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise AIError("INVALID_INPUT", "Provider port is malformed") from exc
        if not 1 <= port <= 65535:
            raise AIError("INVALID_INPUT", "Provider port is out of range")
        if not 0.1 <= timeout <= 120:
            raise AIError("INVALID_INPUT", "Provider timeout is out of range")
        if not isinstance(payload, bytes) or len(payload) > self.max_request_bytes:
            raise AIError("RESOURCE_LIMIT", "Provider request exceeds byte budget")
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or "\r" in key + value
            or "\n" in key + value
            for key, value in headers.items()
        ):
            raise AIError("INVALID_INPUT", "Invalid provider request header")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        if len(path) > 8192 or any(ord(c) < 32 for c in path):
            raise AIError("INVALID_INPUT", "Provider path contains invalid characters")
        candidates = self.resolver.resolve(hostname, port)
        pinned_ip = self._address_set(hostname, candidates, local)
        connection: HTTPConnection | None = None
        total = 0
        try:
            connection = self.factory.create(
                hostname, pinned_ip, port, tls=parsed.scheme == "https", timeout=timeout
            )
            connection.request("POST", path, body=payload, headers=headers)
            response = connection.getresponse()
            status = response.status
            if 300 <= status < 400:
                raise AIError("PERMISSION_DENIED", "HTTP redirect blocked")
            if status in {401, 403}:
                raise AIError("PERMISSION_DENIED", f"Provider HTTP {status}")
            if status == 429:
                raise AIError(
                    "RATE_LIMITED",
                    "Provider rate limit reached",
                    retry_after_seconds=self._retry_after(response),
                )
            if status == 503:
                raise AIError(
                    "SERVICE_UNAVAILABLE",
                    "Provider service unavailable",
                    retry_after_seconds=self._retry_after(response),
                )
            if not 200 <= status < 300:
                raise AIError("PROVIDER_UNAVAILABLE", f"Provider HTTP {status}")
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.max_response_bytes:
                    raise AIError("RESOURCE_LIMIT", "Provider response exceeds byte budget")
                yield bytes(chunk)
        except AIError:
            raise
        except (OSError, TimeoutError, http.client.HTTPException, ssl.SSLError) as exc:
            raise AIError("PROVIDER_UNAVAILABLE", "Provider connection failed") from exc
        finally:
            if connection is not None:
                connection.close()
