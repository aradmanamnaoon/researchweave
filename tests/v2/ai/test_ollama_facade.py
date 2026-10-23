from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from researchweave.ai import build_ai_facade
from researchweave.ai.ollama import OllamaAdapter
from researchweave.ai.policy import ApprovalIssuer, EgressPolicy


class StubTransport:
    def __init__(self):
        self.requests = []

    def send(self, url, headers, payload, timeout):
        self.requests.append((url, json.loads(payload)))
        if url.endswith("/api/embed"):
            return b'{"embeddings":[[3.0,4.0]]}'
        return (
            b'{"model":"fixture","message":{"content":"synthetic local reply"},'
            b'"done":true,"eval_count":6}'
        )


def test_facade_local_inference_requires_exact_host_approval(tmp_path):
    transport = StubTransport()
    issuer = ApprovalIssuer(b"f" * 32)
    ollama = OllamaAdapter("http://127.0.0.1:11434", transport=transport)
    facade = build_ai_facade(tmp_path, issuer=issuer, ollama=ollama)
    chat = {"model": "fixture", "messages": [{"role": "user", "content": "research question"}]}
    context = {"project_id": "study"}
    assert facade.execute("local.chat", chat, context)["error"]["code"] == "NEEDS_APPROVAL"
    assert not transport.requests
    expiry = datetime.now(UTC) + timedelta(minutes=2)
    approval = issuer.issue("study", "local.chat", chat, expiry)
    reply = facade.execute_authorized("local.chat", chat, context, approval=approval)
    assert reply["data"]["text"] == "synthetic local reply"
    assert transport.requests[0][0].endswith("/api/chat")
    changed = {"model": "fixture", "messages": [{"role": "user", "content": "changed"}]}
    assert (
        facade.execute_authorized("local.chat", changed, context, approval=approval)["error"][
            "code"
        ]
        == "PERMISSION_DENIED"
    )
    embedding = {"model": "fixture", "texts": ["memory"], "dimension": 2}
    embed_approval = issuer.issue("study", "local.embed", embedding, expiry)
    vectors = facade.execute_authorized("local.embed", embedding, context, approval=embed_approval)
    assert vectors["data"]["vectors"] == [[0.6, 0.8]]
    facade.close()


def test_facade_disabled_local_models_block_before_transport(tmp_path):
    transport = StubTransport()
    issuer = ApprovalIssuer(b"g" * 32)
    policy = EgressPolicy(allow_local_models=False)
    facade = build_ai_facade(
        tmp_path,
        policy=policy,
        issuer=issuer,
        ollama=OllamaAdapter("http://localhost:11434", policy=policy, transport=transport),
    )
    args = {"model": "fixture", "messages": [{"role": "user", "content": "text"}]}
    approval = issuer.issue("p", "local.chat", args, datetime.now(UTC) + timedelta(minutes=1))
    result = facade.execute_authorized("local.chat", args, {"project_id": "p"}, approval=approval)
    assert result["error"]["code"] == "OFFLINE_DENIED"
    assert not transport.requests
    facade.close()
