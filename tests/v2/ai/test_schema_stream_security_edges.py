import json

import pytest

from researchweave.ai.errors import AIError
from researchweave.ai.policy import EgressPolicy
from researchweave.ai.provider_adapters import (
    LMStudioAdapter,
    OpenAICompatibleAdapter,
    ProviderMessage,
)
from researchweave.ai.provider_services import ModelChooser, ProviderCatalog, ProviderHealthService
from researchweave.ai.streaming import StreamAssembler, sse_events
from researchweave.ai.structured_output import parse_structured_output, validate_schema


class FakeTransport:
    def __init__(self, response: bytes | None = None, error: AIError | None = None):
        self.response = response
        self.error = error

    def send(self, url, headers, payload, timeout):
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("response fixture missing")
        return self.response


def test_structured_output_rejects_parser_ambiguities_and_unsupported_schema() -> None:
    schema = {
        "type": "object",
        "properties": {"value": {"type": "number"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    with pytest.raises(AIError, match="Duplicate JSON property"):
        parse_structured_output('{"value":1,"value":2}', schema)
    with pytest.raises(AIError) as nonfinite:
        parse_structured_output('{"value":NaN}', schema)
    assert nonfinite.value.code == "SCHEMA_MISMATCH"
    with pytest.raises(AIError):
        parse_structured_output("{broken", schema)
    with pytest.raises(AIError) as unsupported:
        validate_schema({"value": 1}, {"type": "object", "oneOf": []})
    assert unsupported.value.code == "INVALID_INPUT"


def test_structured_output_enforces_object_array_string_and_number_bounds() -> None:
    schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["ok"]},
            "fixed": {"type": "integer", "const": 7},
            "names": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {"type": "string", "minLength": 2, "maxLength": 4},
            },
            "score": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["kind", "fixed", "names", "score"],
        "additionalProperties": False,
    }
    valid = {"kind": "ok", "fixed": 7, "names": ["ab"], "score": 0.5}
    validate_schema(valid, schema)
    invalid_values = [
        {**valid, "kind": "bad"},
        {**valid, "fixed": 8},
        {**valid, "names": []},
        {**valid, "names": ["a"]},
        {**valid, "names": ["abcde"]},
        {**valid, "score": -0.1},
        {**valid, "score": 1.1},
        {**valid, "extra": True},
    ]
    for value in invalid_values:
        with pytest.raises(AIError) as exc:
            validate_schema(value, schema)
        assert exc.value.code == "SCHEMA_MISMATCH"
    missing = dict(valid)
    del missing["kind"]
    with pytest.raises(AIError):
        validate_schema(missing, schema)


def test_structured_output_depth_and_size_limits_fail_closed() -> None:
    nested: object = "leaf"
    nested_schema: dict[str, object] = {"type": "string"}
    for _ in range(5):
        nested = [nested]
        nested_schema = {"type": "array", "items": nested_schema}
    with pytest.raises(AIError) as depth:
        validate_schema(nested, nested_schema, max_depth=2)
    assert depth.value.code == "RESOURCE_LIMIT"
    with pytest.raises(AIError) as size:
        parse_structured_output(
            json.dumps({"value": "x" * 100}),
            {"type": "object"},
            max_bytes=10,
        )
    assert size.value.code == "RESOURCE_LIMIT"


def test_sse_decoder_rejects_invalid_utf8_oversize_and_truncation() -> None:
    with pytest.raises(AIError) as invalid_utf8:
        list(sse_events([b"data: \xff\n\n"]))
    assert invalid_utf8.value.code == "SCHEMA_MISMATCH"
    with pytest.raises(AIError) as oversize:
        list(sse_events([b"data: " + b"x" * 20], max_event_bytes=8))
    assert oversize.value.code == "RESOURCE_LIMIT"
    with pytest.raises(AIError) as truncated:
        list(sse_events([b'data: {"choices":[]}\n']))
    assert truncated.value.code == "SCHEMA_MISMATCH"
    with pytest.raises(AIError):
        list(sse_events([b"data: not-json\n\n"]))


@pytest.mark.parametrize(
    ("event", "message"),
    [
        ({"choices": "bad"}, "choices"),
        ({"choices": ["bad"]}, "choice"),
        ({"choices": [{"delta": "bad"}]}, "delta"),
        ({"choices": [{"delta": {"content": 3}}]}, "text"),
        ({"choices": [], "usage": "bad"}, "usage"),
    ],
)
def test_stream_assembler_rejects_malformed_provider_events(event, message) -> None:
    with pytest.raises(AIError, match=message):
        StreamAssembler().feed(event)


def test_stream_assembler_enforces_generated_character_budget() -> None:
    assembler = StreamAssembler(max_characters=3)
    assert assembler.feed({"choices": [{"delta": {"content": "abc"}}]}) == "abc"
    with pytest.raises(AIError) as exc:
        assembler.feed({"choices": [{"delta": {"content": "d"}}]})
    assert exc.value.code == "RESOURCE_LIMIT"


def test_provider_health_explicit_probe_reports_success_and_failure() -> None:
    success = LMStudioAdapter(
        "http://127.0.0.1:1234/v1",
        "local",
        transport=FakeTransport(json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode()),
    )
    failing = OpenAICompatibleAdapter(
        "remote",
        "https://api.example.test/v1",
        "remote-model",
        transport=FakeTransport(error=AIError("RATE_LIMITED", "synthetic")),
    )
    catalog = ProviderCatalog()
    catalog.register(success)
    catalog.register(failing)
    local_health = ProviderHealthService(catalog).probe(
        "lm-studio",
        EgressPolicy(),
        perform_request=True,
    )
    assert local_health.reachable is True
    remote_health = ProviderHealthService(catalog).probe(
        "remote",
        EgressPolicy(offline=False, allowed_hosts=("api.example.test",)),
        perform_request=True,
    )
    assert remote_health.reachable is False
    assert remote_health.error_code == "RATE_LIMITED"


def test_model_chooser_restricted_remote_only_is_denied() -> None:
    catalog = ProviderCatalog()
    catalog.register(
        OpenAICompatibleAdapter(
            "remote",
            "https://api.example.test/v1",
            "remote-model",
            transport=FakeTransport(),
        )
    )
    with pytest.raises(AIError) as exc:
        ModelChooser(catalog).choose(
            ["remote"],
            project_class="restricted",
            offline_only=False,
        )
    assert exc.value.code == "PERMISSION_DENIED"


def test_provider_message_rejects_invalid_role_and_empty_content() -> None:
    with pytest.raises(AIError):
        ProviderMessage("tool", "x").validate()
    with pytest.raises(AIError):
        ProviderMessage("user", "").validate()
