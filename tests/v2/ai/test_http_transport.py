"""No real sockets: deterministic DNS and HTTP connection boundary tests."""

from __future__ import annotations

import pytest

from researchweave.ai.errors import AIError
from researchweave.ai.http_transport import PinnedHTTPTransport


class FakeResolver:
    def __init__(self, addresses: list[str]) -> None:
        self.addresses = addresses
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int) -> list[str]:
        self.calls.append((hostname, port))
        return self.addresses


class FakeHTTPResponse:
    def __init__(self, status: int, data: bytes):
        self.status = status
        self.data = data

    def read(self, size: int) -> bytes:
        return self.data[:size]


class FakeConnection:
    def __init__(self, status: int, data: bytes):
        self.response = FakeHTTPResponse(status, data)
        self.calls: list[tuple[str, str, bytes | None, object]] = []
        self.closed = False

    def request(self, method, url, body=None, headers=None):
        self.calls.append((method, url, body, headers))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class FakeConnectionFactory:
    def __init__(self, status: int = 200, data: bytes = b"ok"):
        self.connections = []
        self.status = status
        self.data = data

    def create(self, hostname, pinned_ip, port, *, tls, timeout):
        connection = FakeConnection(self.status, self.data)
        self.connections.append((hostname, pinned_ip, port, tls, timeout, connection))
        return connection


def test_public_dns_pinning_preserves_tls_host_and_bypasses_proxy():
    resolver = FakeResolver(["8.8.8.8", "1.1.1.1"])
    factory = FakeConnectionFactory(data=b'{"choices":[]}')
    transport = PinnedHTTPTransport(resolver, factory)
    result = transport.send(
        "https://api.example.org/v1/chat/completions?scenario=synthetic",
        {"Authorization": "Bearer SYNTHETIC", "Content-Type": "application/json"},
        b"{}",
        timeout=5,
    )
    assert result == b'{"choices":[]}'
    assert resolver.calls == [("api.example.org", 443)]
    hostname, pinned_ip, port, tls, timeout, connection = factory.connections[0]
    assert hostname == "api.example.org" and pinned_ip == "1.1.1.1"
    assert tls is True and port == 443 and timeout == 5
    assert connection.calls[0][1] == "/v1/chat/completions?scenario=synthetic"
    assert connection.calls[0][2] == b"{}"
    assert connection.closed is True


@pytest.mark.parametrize(
    "addresses", [["8.8.8.8", "10.10.0.2"], ["127.0.0.1"], ["169.254.1.4"], ["garbage"]]
)
def test_remote_private_dns_injection_denied_before_any_network(addresses):
    factory = FakeConnectionFactory()
    resolver = FakeResolver(addresses)
    transport = PinnedHTTPTransport(resolver, factory)
    with pytest.raises(AIError) as error:
        transport.send("https://api.example.org/v1", {}, b"{}", 5)
    assert error.value.code == "PERMISSION_DENIED"
    assert factory.connections == []


def test_http_local_loopback_and_local_resolution_guard():
    factory = FakeConnectionFactory()
    resolver = FakeResolver(["127.0.0.1"])
    transport = PinnedHTTPTransport(resolver, factory)
    assert transport.send("http://localhost:11434/api/tags", {}, b"{}", 2) == b"ok"
    assert factory.connections[0][1] == "127.0.0.1"
    assert factory.connections[0][3] is False
    resolver.addresses = ["8.8.8.8"]
    with pytest.raises(AIError) as error:
        transport.send("http://localhost:11434/api/tags", {}, b"{}", 2)
    assert error.value.code == "PERMISSION_DENIED"
    assert len(factory.connections) == 1


@pytest.mark.parametrize(
    "status,code",
    [
        (301, "PERMISSION_DENIED"),
        (401, "PERMISSION_DENIED"),
        (429, "RATE_LIMITED"),
        (503, "PROVIDER_UNAVAILABLE"),
    ],
)
def test_denied_http_status_is_typed_and_connection_is_closed(status, code):
    factory = FakeConnectionFactory(status=status)
    transport = PinnedHTTPTransport(FakeResolver(["8.8.8.8"]), factory)
    with pytest.raises(AIError) as error:
        transport.send("https://example.org/v1", {}, b"{}", 5)
    assert error.value.code == code
    assert factory.connections[0][-1].closed is True


def test_bounded_provider_reply_and_request_header_injection_blocked():
    factory = FakeConnectionFactory(data=b"x" * 100)
    transport = PinnedHTTPTransport(FakeResolver(["8.8.8.8"]), factory, max_response_bytes=10)
    with pytest.raises(AIError) as error:
        transport.send("https://example.org/v1", {}, b"{}", 5)
    assert error.value.code == "RESOURCE_LIMIT"
    before = len(factory.connections)
    with pytest.raises(AIError) as error:
        transport.send("https://example.org/v1", {"X-Bad": "line\r\nHost: private"}, b"{}", 5)
    assert error.value.code == "INVALID_INPUT"
    assert len(factory.connections) == before
