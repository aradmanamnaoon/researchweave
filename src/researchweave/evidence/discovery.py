"""Opt-in metadata discovery from documented public catalog interfaces.

Adapters are pure Python and depend on an injected HTTPS transport; no socket
is opened at import time, and the default facade never enables remote calls.
Remote metadata is *unverified*, never evidence of scientific claim support.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from .bibliography import normalize_doi
from .errors import EvidenceError, require
from .models import now_utc, sha256

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_QUERY_LENGTH = 500
MAX_RESULTS = 50
MAX_PAGED_RESULTS = 200
MAX_PAGES = 10
MAX_TIMEOUT_SECONDS = 20.0
HOSTS = {
    "crossref": ("api.crossref.org", "/works"),
    "openalex": ("api.openalex.org", "/works"),
    "pubmed": ("eutils.ncbi.nlm.nih.gov", "/entrez/eutils/esearch.fcgi"),
    "europepmc": ("www.ebi.ac.uk", "/europepmc/webservices/rest/search"),
}


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


class HTTPTransport(Protocol):
    def get(self, url: str, *, headers: Mapping[str, str],
            timeout: float) -> HTTPResponse: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: Any, fp: Any, code: Any, msg: Any,
                         headers: Any, newurl: Any) -> None:
        return None


class StdlibHTTPS:
    """Explicit network adapter. Redirects and non-HTTPS URLs are rejected."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(_NoRedirect())

    def get(self, url: str, *, headers: Mapping[str, str],
            timeout: float) -> HTTPResponse:
        parts = urllib.parse.urlsplit(url)
        require(parts.scheme == "https" and parts.hostname in
                {host for host, _ in HOSTS.values()} and
                not parts.username and not parts.password and parts.port is None,
                "Untrusted metadata host", "PERMISSION_DENIED")
        require(0 < timeout <= MAX_TIMEOUT_SECONDS, "Invalid provider timeout")
        request = urllib.request.Request(url, headers=dict(headers), method="GET")  # noqa: S310
        try:
            # Scheme, host, port, userinfo and redirects are validated/blocked above.
            with self._opener.open(request, timeout=timeout) as response:  # noqa: S310
                response_headers = {key.lower(): value for key, value in
                                    response.headers.items()}
                body = response.read(MAX_RESPONSE_BYTES + 1)
                require(len(body) <= MAX_RESPONSE_BYTES,
                        "Metadata provider response exceeds size limit", "RESOURCE_LIMIT")
                return HTTPResponse(response.status, body, response_headers)
        except urllib.error.HTTPError as exc:
            # HTTPError is a response wrapper; reading its bounded body is safe.
            with exc:
                body = exc.read(MAX_RESPONSE_BYTES + 1)
                require(len(body) <= MAX_RESPONSE_BYTES,
                        "Provider error body exceeds limit", "RESOURCE_LIMIT")
                response_headers = {key.lower(): value for key, value in exc.headers.items()}
                return HTTPResponse(exc.code, body, response_headers)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise EvidenceError("PROVIDER_UNAVAILABLE", "Metadata provider unreachable",
                                "Check network access or retry later.") from exc


def _single_string(value: Any) -> str:
    """Retain only safe, bounded plain metadata labels; avoid HTML render decisions."""
    if isinstance(value, list):
        value = next((v for v in value if isinstance(v, str)), "")
    return str(value or "")[:4096] if isinstance(value, str) else ""


def _year(value: Any) -> int | None:
    if isinstance(value, int) and 1500 <= value <= 2200:
        return value
    match = re.search(r"(?:1[5-9]|20|21)\d{2}", str(value or ""))
    return int(match.group()) if match else None


def _authors_crossref(item: Mapping[str, Any]) -> list[str]:
    output: list[str] = []
    for author in item.get("author", [])[:100]:
        if not isinstance(author, dict):
            continue
        name = " ".join(part for part in (author.get("given"), author.get("family"))
                        if isinstance(part, str))
        output.append(name or _single_string(author.get("name")))
    return output


def _crossref(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    message = data.get("message", {})
    if not isinstance(message, dict):
        return []
    items = message.get("items", [])
    if not isinstance(items, list):
        return []
    records: list[dict[str, Any]] = []
    for item in items[:MAX_RESULTS]:
        if not isinstance(item, dict):
            continue
        years = item.get("published", {})
        if not isinstance(years, dict):
            years = {}
        date_parts = years.get("date-parts", [])
        published = (date_parts[0][0] if isinstance(date_parts, list) and date_parts and
                     isinstance(date_parts[0], list) and date_parts[0] else None)
        records.append({"title": _single_string(item.get("title")),
                        "authors": _authors_crossref(item),
                        "doi": normalize_doi(_single_string(item.get("DOI"))),
                        "year": _year(published), "pmid": None,
                        "provider_id": _single_string(item.get("DOI")),
                        "kind": _single_string(item.get("type"))})
    return records


def _openalex(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = data.get("results", [])
    if not isinstance(items, list):
        return []
    records: list[dict[str, Any]] = []
    for item in items[:MAX_RESULTS]:
        if not isinstance(item, dict):
            continue
        authors: list[str] = []
        for authorship in item.get("authorships", [])[:100]:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author", {})
            if isinstance(author, dict):
                name = _single_string(author.get("display_name"))
                if name:
                    authors.append(name)
        records.append({"title": _single_string(item.get("title")),
                        "authors": authors, "year": _year(item.get("publication_year")),
                        "doi": normalize_doi(_single_string(item.get("doi"))),
                        "pmid": None, "provider_id": _single_string(item.get("id")),
                        "kind": _single_string(item.get("type"))})
    return records


def _europepmc(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    block = data.get("resultList", {})
    items = block.get("result", []) if isinstance(block, dict) else []
    if not isinstance(items, list):
        return []
    records: list[dict[str, Any]] = []
    for item in items[:MAX_RESULTS]:
        if not isinstance(item, dict):
            continue
        raw_author = _single_string(item.get("authorString"))
        records.append({"title": _single_string(item.get("title")),
                        "authors": [raw_author] if raw_author else [],
                        "year": _year(item.get("pubYear")),
                        "doi": normalize_doi(_single_string(item.get("doi"))),
                        "pmid": _single_string(item.get("pmid")) or None,
                        "provider_id": _single_string(item.get("id")),
                        "kind": _single_string(item.get("pubType"))})
    return records


def _pubmed(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    block = data.get("result", {})
    if not isinstance(block, dict):
        return []
    uids = block.get("uids", [])
    if not isinstance(uids, list):
        return []
    records: list[dict[str, Any]] = []
    for uid in uids[:MAX_RESULTS]:
        if not isinstance(uid, str) or not uid.isdigit():
            continue
        item = block.get(uid, {})
        if not isinstance(item, dict):
            continue
        authors = [author.get("name") for author in item.get("authors", [])[:100]
                   if isinstance(author, dict) and isinstance(author.get("name"), str)]
        dois = [a.get("value", "") for a in item.get("articleids", [])[:100]
                if isinstance(a, dict) and a.get("idtype") == "doi"]
        records.append({"title": _single_string(item.get("title")), "authors": authors,
                        "year": _year(item.get("pubdate")),
                        "doi": normalize_doi(dois[0]) if dois else None,
                        "pmid": uid, "provider_id": uid,
                        "kind": "pubmed-summary"})
    return records


PARSERS: Mapping[str, Callable[[Mapping[str, Any]], list[dict[str, Any]]]] = {
    "crossref": _crossref, "openalex": _openalex, "europepmc": _europepmc,
    "pubmed": _pubmed,
}


class CatalogClient:
    """Deterministic metadata normalization with bounded, permissioned transport."""

    def __init__(self, transport: HTTPTransport | None = None, *,
                 offline: bool = True, openalex_key: str | None = None,
                 contact_email: str | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 min_interval_seconds: float = 1.0) -> None:
        self.transport = transport
        self.offline = offline
        self.openalex_key = openalex_key
        self.contact_email = contact_email
        self.clock = clock
        self.min_interval_seconds = min_interval_seconds
        self.last_request: dict[str, float] = {}
        self.cooldown_until: dict[str, float] = {}
        self.cache: dict[tuple[str, str, int], dict[str, Any]] = {}

    def _call(self, provider: str, endpoint: str,
              params: Mapping[str, str], headers: Mapping[str, str]) -> tuple[dict[str, Any], str]:
        if self.offline or self.transport is None:
            raise EvidenceError("OFFLINE_DENIED", "Remote catalog access is disabled",
                                "Enable provider access through the trusted host.")
        host, _ = HOSTS[provider]
        require(endpoint.startswith("/") and ".." not in endpoint,
                "Catalog endpoint must be a safe fixed route", "PERMISSION_DENIED")
        uri = f"https://{host}{endpoint}?{urllib.parse.urlencode(params)}"
        require(len(uri) <= 5000, "Provider URL exceeds limit", "RESOURCE_LIMIT")
        response = self.transport.get(uri, headers=headers, timeout=10.0)
        if response.status == 429:
            retry_after = next((value for key, value in response.headers.items()
                                if key.lower() == "retry-after"), "")
            try:
                retry_seconds = min(3600.0, max(1.0, float(retry_after)))
            except ValueError:
                retry_seconds = max(1.0, self.min_interval_seconds)
            self.cooldown_until[provider] = self.clock() + retry_seconds
            raise EvidenceError("RATE_LIMITED", "Provider rejected request rate",
                                "Read Retry-After and retry with a slower cadence.")
        if response.status in {401, 403}:
            raise EvidenceError("PERMISSION_DENIED", "Provider refused credentials or access",
                                "Check provider terms and optional credentials.")
        if not 200 <= response.status < 300:
            raise EvidenceError("PROVIDER_UNAVAILABLE", "Provider returned an error",
                                "Inspect provider availability and retry later.")
        require(len(response.body) <= MAX_RESPONSE_BYTES,
                "Metadata response exceeds size limit", "RESOURCE_LIMIT")
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EvidenceError("PROVIDER_UNAVAILABLE", "Provider response was invalid JSON",
                                "Retry or use locally exported metadata.") from exc
        require(isinstance(payload, dict), "Provider payload is not a JSON object",
                "PROVIDER_UNAVAILABLE")
        return payload, sha256(response.body)

    def search(self, provider: str, query: str, limit: int = 20,
               *, use_cache: bool = True) -> dict[str, Any]:
        require(provider in HOSTS, "Unsupported catalog provider", "UNSUPPORTED_FORMAT")
        require(bool(query.strip()) and len(query) <= MAX_QUERY_LENGTH,
                "Research query must be between 1 and 500 characters")
        require(type(limit) is int and 1 <= limit <= MAX_RESULTS,
                "Result limit must be 1..50")
        if self.offline or self.transport is None:
            raise EvidenceError("OFFLINE_DENIED", "Remote catalog search needs approval",
                                "Use offline references or allow provider access through host.")
        cache_key = (provider, query, limit)
        if use_cache and cache_key in self.cache:
            result = dict(self.cache[cache_key])
            result["cache"] = "memory"
            return result
        instant = self.clock()
        if instant < self.cooldown_until.get(provider, float("-inf")):
            raise EvidenceError("RATE_LIMITED", "Provider requested cooldown",
                                "Retry after the provider's Retry-After interval.")
        previous = self.last_request.get(provider)
        if previous is not None and instant - previous < self.min_interval_seconds:
            raise EvidenceError("RATE_LIMITED", "Provider cooldown has not elapsed",
                                "Wait for the provider's rate window before retrying.")
        self.last_request[provider] = instant
        headers: dict[str, str] = {"Accept": "application/json", "Accept-Encoding": "identity",
                                   "User-Agent": "ResearchWeave/0.1 (opt-in metadata lookup)"}
        host, endpoint = HOSTS[provider]
        if provider == "crossref":
            params = {"query.bibliographic": query, "rows": str(limit)}
            if self.contact_email:
                params["mailto"] = self.contact_email
        elif provider == "openalex":
            params = {"search": query, "per_page": str(limit)}
            if self.openalex_key:
                headers["Authorization"] = f"Bearer {self.openalex_key}"
        elif provider == "europepmc":
            params = {"query": query, "format": "json", "pageSize": str(limit),
                      "resultType": "lite"}
        else:
            params = {"db": "pubmed", "term": query, "retmode": "json",
                      "retmax": str(limit)}
        payload, response_hash = self._call(provider, endpoint, params, headers)
        response_hashes = [response_hash]
        if provider == "pubmed":
            search_block = payload.get("esearchresult", {})
            uids = search_block.get("idlist", []) if isinstance(search_block, dict) else []
            require(isinstance(uids, list) and len(uids) <= limit and
                    all(isinstance(uid, str) and uid.isdigit() for uid in uids),
                    "Invalid PubMed identifier list", "PROVIDER_UNAVAILABLE")
            if uids:
                payload, digest = self._call(
                    provider, "/entrez/eutils/esummary.fcgi",
                    {"db": "pubmed", "id": ",".join(uids), "retmode": "json"}, headers)
                response_hashes.append(digest)
            else:
                payload = {"result": {"uids": []}}
        try:
            records = PARSERS[provider](payload)
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            raise EvidenceError("PROVIDER_UNAVAILABLE", "Malformed metadata record",
                                "Retry or inspect an exported provider response.") from exc
        result = {"provider": provider, "query": query,
                  "fetched_at_utc": now_utc(), "cache": "miss",
                  "raw_response_sha256": response_hashes,
                  "records": [{**r, "provider": provider, "metadata_status": "unverified",
                               "full_text_access": "unknown"} for r in records],
                  "count": len(records), "network_hosts": [host],
                  "scientific_claims_verified": False,
                  "license_note": "Identifier metadata is not proof of full-text availability"}
        self.cache[cache_key] = result
        return result

    def search_pages(
        self,
        provider: str,
        query: str,
        *,
        total_limit: int = 100,
        page_size: int = 25,
    ) -> dict[str, Any]:
        """Fetch several bounded provider pages within one explicit remote operation."""
        require(provider in HOSTS, "Unsupported catalog provider", "UNSUPPORTED_FORMAT")
        require(bool(query.strip()) and len(query) <= MAX_QUERY_LENGTH,
                "Research query must be between 1 and 500 characters")
        require(
            type(total_limit) is int and 1 <= total_limit <= MAX_PAGED_RESULTS,
            "Total result limit must be 1..200",
        )
        require(type(page_size) is int and 1 <= page_size <= MAX_RESULTS,
                "Page size must be 1..50")
        if self.offline or self.transport is None:
            raise EvidenceError(
                "OFFLINE_DENIED",
                "Remote catalog pagination needs approval",
                "Use offline references or allow provider access through host.",
            )
        instant = self.clock()
        if instant < self.cooldown_until.get(provider, float("-inf")):
            raise EvidenceError(
                "RATE_LIMITED",
                "Provider requested cooldown",
                "Retry after the provider's Retry-After interval.",
            )
        previous = self.last_request.get(provider)
        if previous is not None and instant - previous < self.min_interval_seconds:
            raise EvidenceError(
                "RATE_LIMITED",
                "Provider cooldown has not elapsed",
                "Wait for the provider's rate window before retrying.",
            )
        self.last_request[provider] = instant
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": "ResearchWeave/0.1 (opt-in metadata lookup)",
        }
        if provider == "openalex" and self.openalex_key:
            headers["Authorization"] = f"Bearer {self.openalex_key}"
        host, endpoint = HOSTS[provider]
        records: list[dict[str, Any]] = []
        response_hashes: list[str] = []
        pages: list[dict[str, Any]] = []
        token: str | int | None = "*" if provider in {"crossref", "openalex"} else 0
        seen: set[str] = set()
        for page_index in range(MAX_PAGES):
            remaining = total_limit - len(records)
            if remaining <= 0:
                break
            size = min(page_size, remaining)
            if provider == "crossref":
                params = {
                    "query.bibliographic": query,
                    "rows": str(size),
                    "cursor": str(token),
                }
                if self.contact_email:
                    params["mailto"] = self.contact_email
            elif provider == "openalex":
                params = {"search": query, "per_page": str(size), "cursor": str(token)}
            elif provider == "europepmc":
                if not isinstance(token, int):
                    raise EvidenceError(
                        "INTERNAL_ERROR",
                        "Europe PMC pagination token is invalid",
                        "Restart the paged search.",
                    )
                params = {
                    "query": query,
                    "format": "json",
                    "pageSize": str(size),
                    "resultType": "lite",
                    "page": str(token + 1),
                }
            else:
                if not isinstance(token, int):
                    raise EvidenceError(
                        "INTERNAL_ERROR",
                        "PubMed pagination token is invalid",
                        "Restart the paged search.",
                    )
                params = {
                    "db": "pubmed",
                    "term": query,
                    "retmode": "json",
                    "retmax": str(size),
                    "retstart": str(token),
                }
            payload, digest = self._call(provider, endpoint, params, headers)
            response_hashes.append(digest)
            if provider == "pubmed":
                search_block = payload.get("esearchresult", {})
                uids = (
                    search_block.get("idlist", [])
                    if isinstance(search_block, dict)
                    else []
                )
                require(
                    isinstance(uids, list)
                    and len(uids) <= size
                    and all(isinstance(uid, str) and uid.isdigit() for uid in uids),
                    "Invalid PubMed identifier list",
                    "PROVIDER_UNAVAILABLE",
                )
                if uids:
                    payload, summary_hash = self._call(
                        provider,
                        "/entrez/eutils/esummary.fcgi",
                        {"db": "pubmed", "id": ",".join(uids), "retmode": "json"},
                        headers,
                    )
                    response_hashes.append(summary_hash)
                else:
                    payload = {"result": {"uids": []}}
            try:
                page_records = PARSERS[provider](payload)
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                raise EvidenceError(
                    "PROVIDER_UNAVAILABLE",
                    "Malformed metadata record",
                    "Retry or inspect an exported provider response.",
                ) from exc
            added = 0
            for record in page_records:
                identity = (
                    record.get("provider_id")
                    or record.get("doi")
                    or f"{record.get('title')}|{record.get('year')}"
                )
                identity_key = str(identity)
                if identity_key in seen:
                    continue
                seen.add(identity_key)
                records.append({
                    **record,
                    "provider": provider,
                    "metadata_status": "unverified",
                    "full_text_access": "unknown",
                })
                added += 1
                if len(records) >= total_limit:
                    break
            pages.append({
                "page": page_index + 1,
                "returned": len(page_records),
                "added": added,
            })
            if provider == "crossref":
                message = payload.get("message", {})
                next_token = (
                    message.get("next-cursor")
                    if isinstance(message, dict)
                    else None
                )
                token = next_token if isinstance(next_token, str) and next_token else None
            elif provider == "openalex":
                meta = payload.get("meta", {})
                next_token = meta.get("next_cursor") if isinstance(meta, dict) else None
                token = next_token if isinstance(next_token, str) and next_token else None
            elif provider == "europepmc":
                if not isinstance(token, int):
                    raise EvidenceError(
                        "INTERNAL_ERROR",
                        "Europe PMC pagination token is invalid",
                        "Restart the paged search.",
                    )
                token = token + 1 if len(page_records) == size else None
            else:
                if not isinstance(token, int):
                    raise EvidenceError(
                        "INTERNAL_ERROR",
                        "PubMed pagination token is invalid",
                        "Restart the paged search.",
                    )
                token = token + size if len(page_records) == size else None
            if token is None or not page_records:
                break
        return {
            "provider": provider,
            "query": query,
            "records": records,
            "count": len(records),
            "pages": pages,
            "page_count": len(pages),
            "truncated": len(records) >= total_limit,
            "raw_response_sha256": response_hashes,
            "network_hosts": [host],
            "scientific_claims_verified": False,
            "fetched_at_utc": now_utc(),
        }

    def search_batch(
        self,
        provider: str,
        queries: list[str],
        *,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Run bounded independent searches while retaining structured partial failures."""
        require(0 < len(queries) <= 20, "Batch must contain 1 to 20 queries")
        require(len(queries) == len(set(queries)), "Batch queries must be unique")
        successes: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for query in queries:
            try:
                successes.append(self.search(provider, query, limit=limit))
            except EvidenceError as exc:
                failures.append({"query": query, "error": exc.to_dict()})
        return {
            "provider": provider,
            "requested": len(queries),
            "succeeded": len(successes),
            "failed": len(failures),
            "results": successes,
            "failures": failures,
            "partial": bool(successes and failures),
            "scientific_claims_verified": False,
        }
