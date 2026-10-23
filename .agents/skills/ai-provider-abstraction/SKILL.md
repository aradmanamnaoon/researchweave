---
name: ai-provider-abstraction
description: Design a reliable, testable abstraction across hosted AI model providers and capabilities; activate for adding providers, routing model calls, handling quotas, or normalizing AI responses.
---

# AI provider abstraction

Use this skill for services that connect ResearchWeave to hosted language, vision, embedding, reranking, speech, or structured-output models. The abstraction must preserve provider differences where they matter and give the application a stable way to discover supported capabilities. Do not pretend every provider follows one prompt schema or supports identical safety, reasoning, streaming, or cost semantics.

## Define a capability-first interface

Declare a typed provider adapter contract for model discovery, requests, cancellation, streaming events, token accounting, structured output, tool calls, image/audio inputs, embeddings, retryability, and data policies. Keep capabilities explicit per model and provider rather than hardcoding provider names in UI branches. Validate capabilities during configuration and recheck on provider upgrades.

Separate application intent from transport. A request should include operation, messages, system instructions, output format schema, attachment references, context budget, timeouts, user-defined provider restrictions, and an idempotency or trace ID. The adapter translates to provider-specific transport. Return a common response envelope containing generated content, structured tool-call requests, usage where reported, status, provenance, raw provider identifiers, latency, and diagnostics.

Distinguish unsupported capability, invalid credentials, quota exhaustion, rate limit, malformed request, provider outage, content filtering, timeout, and cancellation as separate error categories. Preserve safe original error codes internally while removing tokens or private payloads from diagnostic text.

## Implementation sequence

1. Define protocol types and contract tests without first choosing a dominant provider's schema. Document optional fields as optional; avoid fake zeros for unknown usage.
2. Implement at least two different adapters to expose accidental coupling. Maintain native escapes for provider-specific options under a clearly labeled, validated namespace.
3. Centralize request size checks, schema validation, transport timeouts, cancellation, error mapping, and redaction. Keep authorization and credential lookup outside request bodies.
4. Stream typed incremental events with sequence numbers, completion/failure termination, and partial-response semantics. Do not mistake an interrupted stream for success.
5. Normalize tools into proposals requiring application authorization. Never allow a model adapter to execute tools on its own.
6. Expose routing based on capability, user choice, residency/privacy policy, budget, and availability. Log the rule that selected a provider.

## Cost, reliability, and transparency

Estimate token use where feasible, but keep estimates separate from billed usage. Provider-published prices change; use dated configurable price tables with currency, tier, and unit rather than hardcoded costs in algorithms. Reserve budget before expensive calls and reconcile afterward; handle unavailable usage gracefully. Retries should use exponential backoff with jitter, Retry-After when available, bounded attempts, and idempotency rules. A retry of a nondeterministic generation may produce new content even when no tool side effect occurred.

Failover needs deliberate consent and policy checks: changing providers might move restricted research data across jurisdictions or vendors. Disclose routing and preserve user selection unless an explicit fallback policy permits a change. Track model ID and revision when exposed, request settings, input hashes, and output trace IDs for reproducibility; never claim bitwise determinism merely because temperature is zero.

## Testing and operations

Use mocked HTTP transports for unit tests, malformed event streams, delayed chunks, partial JSON, 429/5xx responses, missing usage, schema violations, and cancellation. Maintain provider contract fixtures for at least one text completion, embedding, streaming response, and structured output when supported. Live smoke tests should run only with opt-in credentials, minimal costs, and provider-specific feature gates. Keep network-based tests out of deterministic CI by default.

Acceptance means adding a new compliant adapter without altering task UI, core workflows, or previously integrated adapters; routing respects privacy and budget; errors remain actionable; cancellation closes resources; sensitive request content is absent from logs. Publish a capability matrix backed by tested behavior.

## Security and references

Encrypt credentials at rest through the platform-approved secret store, never print them, and do not permit untrusted project data to supply API base URLs without SSRF validation. Restrict outbound domains by policy where feasible and sanitize provider metadata before display. Do not simulate consumer subscription access or automate restricted web sessions as a substitute for an authorized API.

References: OpenAI API documentation (https://platform.openai.com/docs/); Anthropic API documentation (https://docs.anthropic.com/); Google Gemini API documentation (https://ai.google.dev/gemini-api/docs); IETF RFC 9110 HTTP semantics (https://www.rfc-editor.org/rfc/rfc9110.html); OpenTelemetry (https://opentelemetry.io/docs/).
