"""Provider contract tests with deterministic, zero-network transports."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from researchweave.evidence import build_evidence_facade
from researchweave.evidence.discovery import (
    CatalogClient,
    HTTPResponse,
    StdlibHTTPS,
)
from researchweave.evidence.errors import EvidenceError


class FixtureTransport:
    def __init__(self, *responses: HTTPResponse) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, str], float]] = []

    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> HTTPResponse:
        self.calls.append((url, dict(headers), timeout))
        assert self.responses, "Unexpected live/extra request"
        return self.responses.pop(0)


def fixture(payload: dict) -> HTTPResponse:
    return HTTPResponse(200, json.dumps(payload).encode("utf-8"))


@pytest.mark.parametrize(
    ("provider", "payload", "expected_id"),
    [
        (
            "crossref",
            {
                "message": {
                    "items": [
                        {
                            "title": ["Synthetic brain study"],
                            "DOI": "10.9999/EXAMPLE",
                            "published": {"date-parts": [[2025, 1]]},
                            "author": [{"given": "Ada", "family": "Researcher"}],
                        }
                    ]
                }
            },
            "10.9999/example",
        ),
        (
            "openalex",
            {
                "results": [
                    {
                        "title": "Synthetic brain study",
                        "doi": "https://doi.org/10.9999/EXAMPLE",
                        "publication_year": 2025,
                        "id": "https://openalex.org/W123",
                        "authorships": [{"author": {"display_name": "Ada Researcher"}}],
                    }
                ]
            },
            "10.9999/example",
        ),
        (
            "europepmc",
            {
                "resultList": {
                    "result": [
                        {
                            "title": "Synthetic brain study",
                            "doi": "10.9999/EXAMPLE",
                            "pubYear": "2025",
                            "pmid": "12345",
                            "authorString": "Researcher A",
                        }
                    ]
                }
            },
            "10.9999/example",
        ),
    ],
)
def test_providers_normalize_without_identity_claims(
    provider: str, payload: dict, expected_id: str
) -> None:
    transport = FixtureTransport(fixture(payload))
    client = CatalogClient(transport, offline=False, min_interval_seconds=0)
    result = client.search(provider, "brain & cognition", limit=3)
    assert result["count"] == 1
    assert result["records"][0]["doi"] == expected_id
    assert result["records"][0]["metadata_status"] == "unverified"
    assert result["scientific_claims_verified"] is False
    assert result["raw_response_sha256"][0]
    assert "brain+%26+cognition" in transport.calls[0][0]
    assert urlsplit(transport.calls[0][0]).scheme == "https"
    assert client.search(provider, "brain & cognition", limit=3)["cache"] == "memory"
    assert len(transport.calls) == 1


def test_pubmed_two_stage_retrieval_without_generated_doi() -> None:
    lookup = fixture({"esearchresult": {"idlist": ["12345"]}})
    summary = fixture(
        {
            "result": {
                "uids": ["12345"],
                "12345": {
                    "title": "Mock example",
                    "pubdate": "2024 Jan",
                    "authors": [{"name": "Synthetic A"}],
                    "articleids": [{"idtype": "pii", "value": "no-doi"}],
                },
            }
        }
    )
    transport = FixtureTransport(lookup, summary)
    client = CatalogClient(transport, offline=False, min_interval_seconds=0)
    output = client.search("pubmed", "test", 5)
    assert output["count"] == 1
    assert output["records"][0]["doi"] is None
    assert output["records"][0]["pmid"] == "12345"
    assert len(output["raw_response_sha256"]) == 2
    assert "esearch.fcgi" in transport.calls[0][0]
    assert parse_qs(urlsplit(transport.calls[1][0]).query)["id"] == ["12345"]


def test_offline_requires_injected_transport_and_explicit_permission(tmp_path: Path) -> None:
    facade = build_evidence_facade(tmp_path, allow_local_writes=True)
    created = facade.execute(
        "project.create", {"title": "Offline", "question": "Why?", "design": "exploratory"}, {}
    )
    project_id = created["data"]["project_id"]
    query = {"project_id": project_id, "provider": "openalex", "query": "cognition"}
    result = facade.execute("discovery.provider_search", query, {})
    assert result["status"] == "failed"
    assert result["error"]["code"] == "OFFLINE_DENIED"
    preview = facade.preview("discovery.provider_search", query, {})
    assert preview["status"] == "ok" and preview["data"]["preview_only"]
    assert not facade.health()["network_enabled"]

    transport = FixtureTransport(fixture({"results": []}))
    granted = build_evidence_facade(
        tmp_path, allow_remote_queries=True, metadata_transport=transport
    )
    result = granted.execute("discovery.provider_search", query, {})
    assert result["status"] == "ok"
    assert result["impact"]["network_hosts"] == ["api.openalex.org"]
    assert len(transport.calls) == 1


def test_invalid_provider_responses_and_rate_limits() -> None:
    for response, code in [
        (HTTPResponse(429, b"exhausted", {"retry-after": "30"}), "RATE_LIMITED"),
        (HTTPResponse(503, b"unavailable"), "PROVIDER_UNAVAILABLE"),
        (HTTPResponse(200, b"{bad json"), "PROVIDER_UNAVAILABLE"),
        (HTTPResponse(200, b"x" * (2 * 1024 * 1024 + 1)), "RESOURCE_LIMIT"),
    ]:
        client = CatalogClient(FixtureTransport(response), offline=False, min_interval_seconds=0)
        with pytest.raises(EvidenceError) as error:
            client.search("crossref", "test")
        assert error.value.code == code


def test_reject_non_https_endpoint_without_network() -> None:
    transport = StdlibHTTPS()
    for url in [
        "http://api.crossref.org/works",
        "https://127.0.0.1/works",
        "https://api.crossref.org:8080/works",
    ]:
        with pytest.raises(EvidenceError) as error:
            transport.get(url, headers={}, timeout=1.0)
        assert error.value.code == "PERMISSION_DENIED"


def test_retry_after_blocks_provider_until_cooldown_expires() -> None:
    now = [100.0]
    transport = FixtureTransport(
        HTTPResponse(429, b"slow", {"Retry-After": "30"}), fixture({"results": []})
    )
    client = CatalogClient(transport, offline=False, clock=lambda: now[0], min_interval_seconds=0)
    with pytest.raises(EvidenceError) as first:
        client.search("openalex", "memory")
    assert first.value.code == "RATE_LIMITED"
    now[0] += 29
    with pytest.raises(EvidenceError) as second:
        client.search("openalex", "memory")
    assert second.value.code == "RATE_LIMITED"
    assert len(transport.calls) == 1
    now[0] += 1
    assert client.search("openalex", "memory")["count"] == 0


def test_malformed_provider_records_are_structured_failure() -> None:
    transport = FixtureTransport(fixture({"message": {"items": [{"author": None}]}}))
    client = CatalogClient(transport, offline=False, min_interval_seconds=0)
    with pytest.raises(EvidenceError) as error:
        client.search("crossref", "synthetic")
    assert error.value.code == "PROVIDER_UNAVAILABLE"


def test_crossref_cursor_pagination_deduplicates_and_stops() -> None:
    first = fixture(
        {
            "message": {
                "items": [
                    {"title": ["First"], "DOI": "10.1000/one"},
                    {"title": ["Duplicate"], "DOI": "10.1000/shared"},
                ],
                "next-cursor": "cursor-2",
            }
        }
    )
    second = fixture(
        {
            "message": {
                "items": [
                    {"title": ["Duplicate"], "DOI": "10.1000/shared"},
                    {"title": ["Second"], "DOI": "10.1000/two"},
                ]
            }
        }
    )
    transport = FixtureTransport(first, second)
    client = CatalogClient(transport, offline=False, min_interval_seconds=0)
    result = client.search_pages("crossref", "synthetic evidence", total_limit=10, page_size=2)
    assert [record["doi"] for record in result["records"]] == [
        "10.1000/one",
        "10.1000/shared",
        "10.1000/two",
    ]
    assert result["page_count"] == 2
    assert parse_qs(urlsplit(transport.calls[0][0]).query)["cursor"] == ["*"]
    assert parse_qs(urlsplit(transport.calls[1][0]).query)["cursor"] == ["cursor-2"]


def test_pubmed_pagination_uses_retstart_and_summary_per_page() -> None:
    responses = [
        fixture({"esearchresult": {"idlist": ["1", "2"]}}),
        fixture(
            {
                "result": {
                    "uids": ["1", "2"],
                    "1": {"title": "One", "pubdate": "2024", "authors": [], "articleids": []},
                    "2": {"title": "Two", "pubdate": "2024", "authors": [], "articleids": []},
                }
            }
        ),
        fixture({"esearchresult": {"idlist": ["3"]}}),
        fixture(
            {
                "result": {
                    "uids": ["3"],
                    "3": {"title": "Three", "pubdate": "2024", "authors": [], "articleids": []},
                }
            }
        ),
    ]
    transport = FixtureTransport(*responses)
    client = CatalogClient(transport, offline=False, min_interval_seconds=0)
    result = client.search_pages("pubmed", "synthetic", total_limit=5, page_size=2)
    assert [record["pmid"] for record in result["records"]] == ["1", "2", "3"]
    search_calls = [call for call in transport.calls if "esearch.fcgi" in call[0]]
    assert parse_qs(urlsplit(search_calls[0][0]).query)["retstart"] == ["0"]
    assert parse_qs(urlsplit(search_calls[1][0]).query)["retstart"] == ["2"]


def test_batch_search_preserves_success_when_an_independent_query_fails() -> None:
    transport = FixtureTransport(
        fixture({"results": [{"id": "W1", "title": "First"}]}),
        HTTPResponse(503, b"down"),
    )
    client = CatalogClient(transport, offline=False, min_interval_seconds=0)
    result = client.search_batch("openalex", ["first", "second"], limit=3)
    assert result["succeeded"] == 1
    assert result["failed"] == 1
    assert result["partial"] is True
    assert result["results"][0]["query"] == "first"
    assert result["failures"][0]["query"] == "second"
    assert result["failures"][0]["error"]["code"] == "PROVIDER_UNAVAILABLE"


@pytest.mark.parametrize(
    ("provider", "responses", "expected_query_fragment"),
    [
        (
            "crossref",
            [fixture({"message": {"DOI": "10.1000/exact", "title": ["Exact"]}})],
            "/works/10.1000%2Fexact",
        ),
        (
            "openalex",
            [
                fixture(
                    {
                        "results": [
                            {
                                "id": "https://openalex.org/W1",
                                "doi": "https://doi.org/10.1000/exact",
                                "title": "Exact",
                            }
                        ]
                    }
                )
            ],
            "filter=doi%3Ahttps%3A%2F%2Fdoi.org%2F10.1000%2Fexact",
        ),
        (
            "europepmc",
            [
                fixture(
                    {
                        "resultList": {
                            "result": [
                                {
                                    "id": "1",
                                    "doi": "10.1000/exact",
                                    "title": "Exact",
                                }
                            ]
                        }
                    }
                )
            ],
            "query=DOI%3A10.1000%2Fexact",
        ),
    ],
)
def test_exact_doi_lookup_uses_provider_specific_identity_query(
    provider: str,
    responses: list[HTTPResponse],
    expected_query_fragment: str,
) -> None:
    transport = FixtureTransport(*responses)
    result = CatalogClient(transport, offline=False, min_interval_seconds=0).lookup_doi(
        provider, "https://doi.org/10.1000/EXACT"
    )
    assert result["catalog_presence"] == "reported"
    assert result["candidate_count"] == 1
    assert result["records"][0]["doi"] == "10.1000/exact"
    assert expected_query_fragment in transport.calls[0][0]


def test_pubmed_exact_doi_lookup_throttles_each_http_request() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    transport = FixtureTransport(
        fixture({"esearchresult": {"idlist": ["123"]}}),
        fixture(
            {
                "result": {
                    "uids": ["123"],
                    "123": {
                        "title": "Exact",
                        "articleids": [{"idtype": "doi", "value": "10.1000/exact"}],
                    },
                }
            }
        ),
    )
    client = CatalogClient(
        transport,
        offline=False,
        clock=lambda: now[0],
        sleeper=sleep,
        min_interval_seconds=0.5,
    )
    result = client.lookup_doi("pubmed", "10.1000/exact")
    assert result["catalog_presence"] == "reported"
    assert sleeps == [0.5]
    assert "term=%2210.1000%2Fexact%22%5Baid%5D" in transport.calls[0][0]


def test_provider_credentials_and_paged_search_are_available_through_public_facade(
    tmp_path: Path,
) -> None:
    transport = FixtureTransport(
        fixture(
            {
                "results": [{"id": "W1", "title": "One", "doi": "10.1000/one"}],
                "meta": {"next_cursor": None},
            }
        )
    )
    facade = build_evidence_facade(
        tmp_path,
        allow_local_writes=True,
        allow_remote_queries=True,
        metadata_transport=transport,
        openalex_key="fixture-key",
        contact_email="researcher@example.org",
        provider_min_interval_seconds=0,
    )
    project_id = facade.execute(
        "project.create",
        {"title": "Paged", "question": "What exists?", "design": "exploratory"},
        {},
    )["data"]["project_id"]
    result = facade.execute(
        "discovery.provider_search_pages",
        {
            "project_id": project_id,
            "provider": "openalex",
            "query": "cognition",
            "total_limit": 10,
            "page_size": 5,
        },
        {},
    )
    assert result["status"] == "ok", result
    assert result["data"]["count"] == 1
    assert transport.calls[0][1]["Authorization"] == "Bearer fixture-key"
    manifest = {item["operation"]: item for item in facade.capability_manifest()}[
        "discovery.provider_search_pages"
    ]
    properties = manifest["arguments_schema"]["properties"]
    assert properties["total_limit"]["maximum"] == 200
    assert properties["page_size"]["maximum"] == 50
