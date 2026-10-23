---
name: local-llm-integration
description: Integrate locally running language models safely and efficiently across resource-constrained desktop systems; activate for Ollama, llama.cpp, local embeddings, inference settings, or offline model workflows.
---

# Local LLM integration

Apply this skill when ResearchWeave discovers, connects to, or manages a local inference runtime. Support configurable integrations such as llama.cpp-compatible servers, Ollama, or an embedded backend only where installation, licensing, and platform support are verified. Treat local deployment as a distinct capability with its own performance, memory, and lifecycle requirements.

## Runtime and model discovery

Probe a configured localhost endpoint with a short deadline and explicit protocol detection; never scan arbitrary ports on the user's network. A provider may be reachable but not own the listed models, or may require authentication despite being local. Separate runtime availability from model availability and feature readiness.

Maintain a model descriptor that records family, exact artifact identifier, digest if exposed, parameter count when known, quantization, tokenizer, context capacity, generation format, embedding dimensions, and runtime backend version. Model marketing names are insufficient for repeatability. Label self-reported metadata and unknown fields honestly. Validate model licenses and redistribution constraints before proposing bundled downloads.

Check whether the runtime exposes text, JSON schema, tool-call markup, embeddings, vision, or audio. Capability verification should involve lightweight behavior tests, because advertised API compatibility may hide major semantic differences. Avoid promising structured output from a model that emits unvalidated free text.

## Performance and resource control

Estimate total RAM or VRAM from quantized weights, context KV cache, runtime buffers, concurrent sessions, and embedding jobs. Present conservative configuration choices on low-memory systems; do not automatically download multi-gigabyte models or saturate hardware. Support explicit CPU-only operation, device selection when exposed, concurrency limits, context budgets, batch/threads controls, and adaptive memory caps.

Keep token generation asynchronous to the desktop UI. Stream incremental text with responsive stop control. Release subprocesses, file handles, and GPU resources on cancellation and application exit. Configure idle unload where supported. Explain the difference between load time, prompt processing time, and generation rate. Benchmark with fixed prompts and report tokens per second only when token counts and measurement boundaries are known.

Do not persist large hidden chain-of-thought traces by default. Separate model output from application event logs and purge temporary model inputs according to user retention settings.

## Offline and grounded research behavior

Support local retrieval and embeddings without background cloud calls. Audit the entire workflow for implicit network dependencies: tokenizer acquisition, telemetry, PDF converters, OCR, speech services, auto-updates, and fallbacks. When offline mode is selected, refuse cloud fallback and show a local actionable error if a required model is missing.

Use the same source-grounding contracts as hosted generation: every citation must resolve to an indexed source span, and a model's fabricated citation strings must never become trusted references. Maintain a prompt and retrieval manifest including local model hash, document digests, chunking configuration, embedding model identity, and generation parameters. Quantization changes may change behavior; do not claim deterministic output across hardware backends.

## Trust and network boundaries

Bind local HTTP services to loopback unless the user explicitly configures remote serving and understands exposure. Authenticate access where supported, especially for endpoints that can trigger downloads or model loading. Validate user-supplied endpoints and block loopback-to-private-network expansion by untrusted imported projects. Never execute text returned by a model as a shell command without separate application authorization.

Downloaded model artifacts are untrusted binaries or serialized structures. Prefer safe tensor formats and fixed-model loaders; avoid arbitrary pickle deserialization. Verify declared checksums and use an allowlisted source catalog where possible. Do not silently trust community model prompts as application instructions.

## Test matrix and acceptance

Test runtime absent, daemon starting, stale model catalog, unauthorized endpoint, incompatible API shape, malformed stream, cancellation during load, disk full, model unload, and concurrent requests. Exercise at least one CPU-only configuration and one realistic low-memory fixture, using mocks for CI and opt-in real-runtime smoke tests.

Acceptance requires successful model selection and generation after restart, reliable offline mode, bounded resource use, validated local citations, traceable model identity, secure endpoint defaults, and a clear diagnostic when the machine cannot support a selected model.

References: Ollama API (https://docs.ollama.com/api); llama.cpp repository and server guidance (https://github.com/ggml-org/llama.cpp); Hugging Face model cards (https://huggingface.co/docs/hub/model-cards); safetensors (https://huggingface.co/docs/safetensors/).
