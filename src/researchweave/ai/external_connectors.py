from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote

from .errors import AIError
from .policy import EgressPolicy, validate_endpoint
from .structured_output import validate_schema


@dataclass(frozen=True)
class ConnectorResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class ConnectorTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        *,
        timeout: float,
        max_bytes: int,
    ) -> ConnectorResponse: ...


@dataclass(frozen=True)
class ConnectorManifest:
    identifier: str
    description: str
    read_scopes: tuple[str, ...]
    write_scopes: tuple[str, ...]
    network: bool
    local_only: bool
    configured: bool


class ConnectorRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ConnectorManifest] = {}

    def register(self, manifest: ConnectorManifest) -> None:
        if not manifest.identifier or manifest.identifier in self._items:
            raise AIError("CONFLICT", "Connector is empty or already registered")
        self._items[manifest.identifier] = manifest

    def list(self) -> list[ConnectorManifest]:
        return [self._items[key] for key in sorted(self._items)]

    def require(self, identifier: str) -> ConnectorManifest:
        try:
            return self._items[identifier]
        except KeyError as exc:
            raise AIError("NOT_FOUND", "Connector is not registered") from exc


def _decode_json(response: ConnectorResponse, provider: str) -> Any:
    if response.status in {401, 403}:
        raise AIError("PERMISSION_DENIED", f"{provider} rejected credentials")
    if response.status == 404:
        raise AIError("NOT_FOUND", f"{provider} resource was not found")
    if response.status == 409 or response.status == 412:
        raise AIError("CONFLICT", f"{provider} remote revision changed")
    if response.status == 429:
        raise AIError("RATE_LIMITED", f"{provider} rate limit reached")
    if not 200 <= response.status < 300:
        raise AIError("PROVIDER_UNAVAILABLE", f"{provider} HTTP {response.status}")
    try:
        return json.loads(response.body)
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise AIError("SCHEMA_MISMATCH", f"{provider} returned malformed JSON") from exc


@dataclass(frozen=True)
class ZoteroItem:
    key: str
    version: int
    item_type: str
    title: str
    creators: tuple[str, ...]
    doi: str | None


class ZoteroConnector:
    """Typed Zotero local/Web API adapter with explicit write scope."""

    def __init__(
        self,
        endpoint: str,
        *,
        library_id: str,
        library_type: str = "users",
        api_key: str | None = None,
        local: bool = False,
        transport: ConnectorTransport,
    ) -> None:
        if library_type not in {"users", "groups"}:
            raise AIError("INVALID_INPUT", "Unsupported Zotero library type")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", library_id):
            raise AIError("INVALID_INPUT", "Invalid Zotero library ID")
        self.endpoint = validate_endpoint(endpoint, local=local).rstrip("/")
        self.library_id = library_id
        self.library_type = library_type
        self.api_key = api_key
        self.local = local
        self.transport = transport

    def manifest(self) -> ConnectorManifest:
        return ConnectorManifest(
            identifier="zotero",
            description="Zotero bibliographic library",
            read_scopes=("zotero.read",),
            write_scopes=("zotero.write",),
            network=True,
            local_only=self.local,
            configured=self.local or bool(self.api_key),
        )

    def _headers(self, *, write_token: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json", "Zotero-API-Version": "3"}
        if self.api_key:
            headers["Zotero-API-Key"] = self.api_key
        if write_token:
            headers["X-ResearchWeave-Approval"] = write_token
        return headers

    def _base(self) -> str:
        return f"{self.endpoint}/{self.library_type}/{self.library_id}"

    @staticmethod
    def _parse_item(value: Any) -> ZoteroItem:
        if not isinstance(value, Mapping):
            raise AIError("SCHEMA_MISMATCH", "Zotero item is not an object")
        try:
            data = value["data"]
            if not isinstance(data, Mapping):
                raise TypeError
            key = value.get("key", data.get("key"))
            version = value.get("version", data.get("version"))
            item_type = data["itemType"]
            title = data.get("title", "")
            creators_raw = data.get("creators", [])
            if (
                not isinstance(key, str)
                or type(version) is not int
                or not isinstance(item_type, str)
                or not isinstance(title, str)
                or not isinstance(creators_raw, list)
            ):
                raise TypeError
            creators = []
            for creator in creators_raw:
                if not isinstance(creator, Mapping):
                    continue
                if isinstance(creator.get("name"), str):
                    creators.append(str(creator["name"]))
                else:
                    creators.append(
                        " ".join(
                            part
                            for part in (
                                str(creator.get("firstName", "")).strip(),
                                str(creator.get("lastName", "")).strip(),
                            )
                            if part
                        )
                    )
            doi = data.get("DOI")
            if doi is not None and not isinstance(doi, str):
                raise TypeError
        except (KeyError, TypeError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Zotero item schema is malformed") from exc
        return ZoteroItem(key, version, item_type, title, tuple(creators), doi)

    def list_items(
        self,
        policy: EgressPolicy,
        *,
        limit: int = 100,
        start: int = 0,
    ) -> list[ZoteroItem]:
        if not 1 <= limit <= 100 or not 0 <= start <= 1_000_000:
            raise AIError("INVALID_INPUT", "Invalid Zotero pagination")
        policy.permit(self.endpoint, local=self.local)
        response = self.transport.request(
            "GET",
            f"{self._base()}/items?limit={limit}&start={start}&format=json",
            self._headers(),
            None,
            timeout=20,
            max_bytes=5_000_000,
        )
        decoded = _decode_json(response, "Zotero")
        if not isinstance(decoded, list) or len(decoded) > limit:
            raise AIError("SCHEMA_MISMATCH", "Zotero item list is malformed")
        return [self._parse_item(item) for item in decoded]

    def create_item(
        self,
        policy: EgressPolicy,
        item: Mapping[str, Any],
        *,
        approval_token: str | None,
    ) -> str:
        if not approval_token:
            raise AIError("NEEDS_APPROVAL", "Zotero writes require a trusted approval token")
        policy.permit(self.endpoint, local=self.local)
        body = json.dumps([dict(item)], ensure_ascii=False, allow_nan=False).encode()
        if len(body) > 1_000_000:
            raise AIError("RESOURCE_LIMIT", "Zotero write payload exceeds limit")
        response = self.transport.request(
            "POST",
            f"{self._base()}/items",
            {**self._headers(write_token=approval_token), "Content-Type": "application/json"},
            body,
            timeout=20,
            max_bytes=2_000_000,
        )
        decoded = _decode_json(response, "Zotero")
        if not isinstance(decoded, Mapping):
            raise AIError("SCHEMA_MISMATCH", "Zotero write receipt is malformed")
        successful = decoded.get("successful")
        if not isinstance(successful, Mapping) or not successful:
            raise AIError("PROVIDER_UNAVAILABLE", "Zotero did not confirm the write")
        first = next(iter(successful.values()))
        if not isinstance(first, Mapping) or not isinstance(first.get("key"), str):
            raise AIError("SCHEMA_MISMATCH", "Zotero write receipt lacks item key")
        return str(first["key"])


@dataclass(frozen=True)
class PaperRecord:
    provider: str
    provider_id: str
    title: str
    doi: str | None
    authors: tuple[str, ...]
    publication_year: int | None
    venue: str | None
    abstract: str | None
    retrieved_at: str


class ScholarlyMetadataConnector:
    """Crossref DOI and OpenAlex work metadata normalization."""

    def __init__(
        self,
        *,
        crossref_endpoint: str = "https://api.crossref.org",
        openalex_endpoint: str = "https://api.openalex.org",
        transport: ConnectorTransport,
    ) -> None:
        self.crossref_endpoint = validate_endpoint(crossref_endpoint).rstrip("/")
        self.openalex_endpoint = validate_endpoint(openalex_endpoint).rstrip("/")
        self.transport = transport

    @staticmethod
    def _normalize_doi(doi: str) -> str:
        normalized = doi.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
        if not re.fullmatch(r"10\.\d{4,9}/\S+", normalized):
            raise AIError("INVALID_INPUT", "Malformed DOI")
        return normalized

    def resolve_doi(self, doi: str, policy: EgressPolicy) -> PaperRecord:
        normalized = self._normalize_doi(doi)
        policy.permit(self.crossref_endpoint, local=False)
        response = self.transport.request(
            "GET",
            self.crossref_endpoint + "/works/" + quote(normalized, safe=""),
            {"Accept": "application/json"},
            None,
            timeout=20,
            max_bytes=4_000_000,
        )
        decoded = _decode_json(response, "Crossref")
        try:
            message = decoded["message"]
            if not isinstance(message, Mapping):
                raise TypeError
            title_values = message.get("title")
            title = title_values[0] if isinstance(title_values, list) and title_values else None
            if not isinstance(title, str):
                raise TypeError
            authors = []
            for author in message.get("author", []):
                if isinstance(author, Mapping):
                    full = " ".join(
                        part
                        for part in (
                            str(author.get("given", "")).strip(),
                            str(author.get("family", "")).strip(),
                        )
                        if part
                    )
                    if full:
                        authors.append(full)
            published = message.get("published-print") or message.get("published-online")
            year: int | None = None
            if isinstance(published, Mapping):
                date_parts = published.get("date-parts")
                if (
                    isinstance(date_parts, list)
                    and date_parts
                    and isinstance(date_parts[0], list)
                    and date_parts[0]
                    and type(date_parts[0][0]) is int
                ):
                    year = int(date_parts[0][0])
            container = message.get("container-title")
            venue = container[0] if isinstance(container, list) and container else None
        except (KeyError, TypeError, IndexError) as exc:
            raise AIError("SCHEMA_MISMATCH", "Crossref work schema is malformed") from exc
        return PaperRecord(
            provider="crossref",
            provider_id=normalized,
            title=title,
            doi=normalized,
            authors=tuple(authors),
            publication_year=year,
            venue=venue if isinstance(venue, str) else None,
            abstract=message.get("abstract") if isinstance(message.get("abstract"), str) else None,
            retrieved_at=datetime.now(UTC).isoformat(),
        )

    def openalex_work(self, work_id: str, policy: EgressPolicy) -> PaperRecord:
        if not re.fullmatch(r"W\d{1,20}", work_id):
            raise AIError("INVALID_INPUT", "Invalid OpenAlex work identifier")
        policy.permit(self.openalex_endpoint, local=False)
        response = self.transport.request(
            "GET",
            self.openalex_endpoint + "/works/" + work_id,
            {"Accept": "application/json"},
            None,
            timeout=20,
            max_bytes=4_000_000,
        )
        decoded = _decode_json(response, "OpenAlex")
        if not isinstance(decoded, Mapping):
            raise AIError("SCHEMA_MISMATCH", "OpenAlex work schema is malformed")
        title = decoded.get("title")
        if not isinstance(title, str):
            raise AIError("SCHEMA_MISMATCH", "OpenAlex work has no valid title")
        authors = []
        for authorship in decoded.get("authorships", []):
            if isinstance(authorship, Mapping):
                author = authorship.get("author")
                if isinstance(author, Mapping) and isinstance(author.get("display_name"), str):
                    authors.append(str(author["display_name"]))
        ids = decoded.get("ids")
        doi = None
        if isinstance(ids, Mapping) and isinstance(ids.get("doi"), str):
            raw_doi = str(ids["doi"])
            try:
                doi = self._normalize_doi(raw_doi)
            except AIError:
                doi = None
        year = decoded.get("publication_year")
        return PaperRecord(
            provider="openalex",
            provider_id=work_id,
            title=title,
            doi=doi,
            authors=tuple(authors),
            publication_year=year if type(year) is int else None,
            venue=None,
            abstract=None,
            retrieved_at=datetime.now(UTC).isoformat(),
        )


@dataclass(frozen=True)
class RemoteObject:
    key: str
    etag: str
    size: int
    sha256: str


class WebDAVConnector:
    def __init__(
        self,
        endpoint: str,
        *,
        username: str | None = None,
        password: str | None = None,
        transport: ConnectorTransport,
    ) -> None:
        self.endpoint = validate_endpoint(endpoint).rstrip("/")
        self.username = username
        self.password = password
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/octet-stream"}
        if self.username or self.password:
            token = hashlib.sha256(
                f"{self.username or ''}:{self.password or ''}".encode()
            ).hexdigest()
            headers["X-ResearchWeave-Credential-Ref"] = token
        return headers

    @staticmethod
    def _safe_key(key: str) -> str:
        if not key or ".." in key or key.startswith("/") or "\\" in key:
            raise AIError("INVALID_INPUT", "Unsafe WebDAV object key")
        return "/".join(quote(part, safe="._-") for part in key.split("/"))

    def get(self, key: str, policy: EgressPolicy) -> tuple[bytes, RemoteObject]:
        policy.permit(self.endpoint, local=False)
        response = self.transport.request(
            "GET",
            self.endpoint + "/" + self._safe_key(key),
            self._headers(),
            None,
            timeout=30,
            max_bytes=24_000_000,
        )
        if response.status == 404:
            raise AIError("NOT_FOUND", "WebDAV object does not exist")
        if not 200 <= response.status < 300:
            _decode_json(response, "WebDAV")
        etag = response.headers.get("ETag")
        if not etag:
            raise AIError("SCHEMA_MISMATCH", "WebDAV object response lacks ETag")
        digest = hashlib.sha256(response.body).hexdigest()
        declared = response.headers.get("Digest-SHA256")
        if declared is not None and declared != digest:
            raise AIError("INTEGRITY_FAILURE", "WebDAV content digest mismatch")
        return response.body, RemoteObject(key, etag, len(response.body), digest)

    def put(
        self,
        key: str,
        content: bytes,
        policy: EgressPolicy,
        *,
        expected_etag: str | None,
    ) -> RemoteObject:
        if not content or len(content) > 24_000_000:
            raise AIError("RESOURCE_LIMIT", "WebDAV object exceeds upload budget")
        policy.permit(self.endpoint, local=False)
        digest = hashlib.sha256(content).hexdigest()
        headers = {
            **self._headers(),
            "Content-Type": "application/octet-stream",
            "Digest-SHA256": digest,
            "If-Match": expected_etag if expected_etag is not None else "*",
        }
        response = self.transport.request(
            "PUT",
            self.endpoint + "/" + self._safe_key(key),
            headers,
            content,
            timeout=60,
            max_bytes=1_000_000,
        )
        if response.status in {409, 412}:
            raise AIError("CONFLICT", "WebDAV object changed during upload")
        if not 200 <= response.status < 300:
            _decode_json(response, "WebDAV")
        etag = response.headers.get("ETag")
        if not etag:
            raise AIError("SCHEMA_MISMATCH", "WebDAV write receipt lacks ETag")
        return RemoteObject(key, etag, len(content), digest)


class S3ObjectBackend(Protocol):
    def get_object(self, bucket: str, key: str) -> tuple[bytes, str]: ...

    def put_object(
        self,
        bucket: str,
        key: str,
        body: bytes,
        *,
        expected_version: str | None,
    ) -> str: ...


class S3CompatibleConnector:
    """Host-injected S3-compatible object API; never creates paid resources."""

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key_ref: str,
        backend: S3ObjectBackend,
    ) -> None:
        self.endpoint = validate_endpoint(endpoint)
        if not bucket or not access_key_ref:
            raise AIError(
                "CREDENTIAL_REQUIRED",
                "S3 connector requires explicit bucket and opaque access-key reference",
            )
        self.bucket = bucket
        self.access_key_ref = access_key_ref
        self.backend = backend

    def get(self, key: str) -> tuple[bytes, RemoteObject]:
        data, version = self.backend.get_object(self.bucket, key)
        digest = hashlib.sha256(data).hexdigest()
        return data, RemoteObject(key, version, len(data), digest)

    def put(
        self,
        key: str,
        content: bytes,
        *,
        expected_version: str | None,
    ) -> RemoteObject:
        if not content or len(content) > 24_000_000:
            raise AIError("RESOURCE_LIMIT", "S3 object exceeds upload budget")
        version = self.backend.put_object(
            self.bucket,
            key,
            content,
            expected_version=expected_version,
        )
        return RemoteObject(
            key,
            version,
            len(content),
            hashlib.sha256(content).hexdigest(),
        )


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    effect: str
    required_scope: str


class MCPServer(Protocol):
    def list_tools(self) -> Sequence[Mapping[str, Any]]: ...

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]: ...


class MCPBridge:
    _EFFECTS = {"read", "local-write", "external-network", "irreversible"}

    def __init__(
        self,
        server: MCPServer,
        *,
        allowed_tools: Mapping[str, tuple[str, str]],
    ) -> None:
        self.server = server
        self.allowed_tools = dict(allowed_tools)
        self._tools: dict[str, MCPTool] = {}

    def inspect(self) -> list[MCPTool]:
        discovered = self.server.list_tools()
        tools: list[MCPTool] = []
        for raw in discovered:
            if not isinstance(raw, Mapping):
                raise AIError("SCHEMA_MISMATCH", "MCP tool manifest is malformed")
            name = raw.get("name")
            schema = raw.get("inputSchema")
            description = raw.get("description", "")
            if not isinstance(name, str) or not isinstance(schema, Mapping):
                raise AIError("SCHEMA_MISMATCH", "MCP tool manifest is malformed")
            policy = self.allowed_tools.get(name)
            if policy is None:
                continue
            effect, scope = policy
            if effect not in self._EFFECTS:
                raise AIError("INVALID_INPUT", "Host MCP effect policy is invalid")
            tool = MCPTool(name, str(description), dict(schema), effect, scope)
            tools.append(tool)
            self._tools[name] = tool
        return tools

    def invoke(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        granted_scopes: Sequence[str],
    ) -> Mapping[str, Any]:
        if not self._tools:
            self.inspect()
        tool = self._tools.get(name)
        if tool is None:
            raise AIError("PERMISSION_DENIED", "MCP tool is not host-allowlisted")
        if tool.required_scope not in granted_scopes:
            raise AIError("PERMISSION_DENIED", "MCP scope was not granted")
        validate_schema(dict(arguments), tool.input_schema)
        result = self.server.call_tool(name, dict(arguments))
        if not isinstance(result, Mapping):
            raise AIError("SCHEMA_MISMATCH", "MCP tool returned malformed result")
        return {
            "tool": name,
            "effect": tool.effect,
            "untrusted_result": dict(result),
            "authority_changed": False,
        }
