//! Offline-first model adapters: validated profiles and proposal-only tool output.
//! The host owns user approval, transport credentials and tool execution.
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

pub mod agent_actions;
pub mod contextual;
pub mod conversations;
pub mod grounding;
pub mod operations;
pub mod profile_store;
pub mod prompts;

#[derive(Debug, Error, PartialEq, Eq)]
pub enum AiError {
    #[error("offline policy denies external requests")]
    Offline,
    #[error("model capability unavailable")]
    UnsupportedCapability,
    #[error("invalid provider configuration or response")]
    Invalid,
    #[error("request cancelled")]
    Cancelled,
    #[error("provider rate limited")]
    RateLimited,
    #[error("provider temporarily unavailable")]
    Unavailable,
    #[error("provider transport failed")]
    Transport,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Capabilities {
    pub streaming: bool,
    pub tools: bool,
    pub structured_output: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProviderKind {
    OpenAiCompatible,
    Ollama,
    Anthropic,
    Gemini,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProviderProfile {
    pub id: String,
    pub kind: ProviderKind,
    pub model: String,
    pub endpoint: String,
    pub local: bool,
    pub credential_reference: Option<String>,
    pub capabilities: Capabilities,
}

impl ProviderProfile {
    pub fn validate(&self) -> Result<(), AiError> {
        if self.id.is_empty()
            || self.id.len() > 96
            || self.model.trim().is_empty()
            || self.model.len() > 200
            || self.endpoint.contains('@')
            || self.endpoint.contains('?')
            || self.endpoint.contains('#')
            || self
                .credential_reference
                .as_ref()
                .is_some_and(|v| v.is_empty() || v.len() > 200)
        {
            return Err(AiError::Invalid);
        }
        let secure = self.endpoint.starts_with("https://");
        let loopback = self.endpoint.starts_with("http://localhost:")
            || self.endpoint.starts_with("http://127.0.0.1:")
            || self.endpoint.starts_with("http://[::1]:");
        if !secure && !loopback {
            return Err(AiError::Invalid);
        }
        if self.local && !loopback {
            return Err(AiError::Invalid);
        }
        if matches!(self.kind, ProviderKind::Ollama) && !self.local {
            return Err(AiError::Invalid);
        }
        if matches!(self.kind, ProviderKind::Anthropic | ProviderKind::Gemini) && self.local {
            return Err(AiError::Invalid);
        }
        if self.model.contains('/') && matches!(self.kind, ProviderKind::Gemini)
            || self
                .model
                .chars()
                .any(|c| c.is_control() || c.is_whitespace())
        {
            return Err(AiError::Invalid);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy)]
pub struct EgressPolicy {
    pub offline: bool,
    pub external_allowed: bool,
}
impl EgressPolicy {
    pub fn authorize(&self, profile: &ProviderProfile) -> Result<(), AiError> {
        profile.validate()?;
        if !profile.local && (self.offline || !self.external_allowed) {
            return Err(AiError::Offline);
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Usage {
    pub prompt_tokens: Option<u64>,
    pub completion_tokens: Option<u64>,
    pub total_tokens: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ToolProposal {
    pub call_id: String,
    pub operation: String,
    pub arguments: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Response {
    pub text: String,
    pub usage: Option<Usage>,
    pub proposals: Vec<ToolProposal>,
}

pub trait Transport {
    fn post_json(&self, endpoint: &str, body: &Value) -> Result<(u16, Value), AiError>;
    fn post_json_headers(
        &self,
        endpoint: &str,
        body: &Value,
        headers: &[(&str, &str)],
    ) -> Result<(u16, Value), AiError> {
        if !headers.is_empty() {
            return Err(AiError::UnsupportedCapability);
        }
        self.post_json(endpoint, body)
    }
}

/// Blocking, size-bounded HTTP transport. No credential header is synthesized.
/// The host must resolve credential references separately before remote use.
pub struct NativeHttpTransport {
    agent: ureq::Agent,
}

impl NativeHttpTransport {
    pub fn new(timeout: std::time::Duration) -> Result<Self, AiError> {
        if timeout.is_zero() || timeout > std::time::Duration::from_secs(120) {
            return Err(AiError::Invalid);
        }
        Ok(Self {
            agent: ureq::AgentBuilder::new()
                .timeout(timeout)
                .redirects(0)
                .build(),
        })
    }
}

impl Transport for NativeHttpTransport {
    fn post_json(&self, endpoint: &str, body: &Value) -> Result<(u16, Value), AiError> {
        self.post_json_headers(endpoint, body, &[])
    }

    fn post_json_headers(
        &self,
        endpoint: &str,
        body: &Value,
        headers: &[(&str, &str)],
    ) -> Result<(u16, Value), AiError> {
        let url = url::Url::parse(endpoint).map_err(|_| AiError::Invalid)?;
        let host = url.host_str().ok_or(AiError::Invalid)?;
        let loopback = matches!(host, "127.0.0.1" | "localhost" | "[::1]" | "::1");
        if !(url.scheme() == "https" || (url.scheme() == "http" && loopback))
            || !url.username().is_empty()
            || url.password().is_some()
            || url.query().is_some()
            || url.fragment().is_some()
        {
            return Err(AiError::Invalid);
        }
        let encoded = serde_json::to_vec(body).map_err(|_| AiError::Invalid)?;
        if encoded.len() > 1_000_000 {
            return Err(AiError::Invalid);
        }
        let mut request = self
            .agent
            .post(endpoint)
            .set("Content-Type", "application/json");
        for (name, value) in headers {
            if !matches!(
                *name,
                "Authorization" | "x-api-key" | "anthropic-version" | "x-goog-api-key"
            ) || value.is_empty()
                || value.chars().any(|c| c.is_control())
            {
                return Err(AiError::Invalid);
            }
            request = request.set(name, value);
        }
        let response = request.send_bytes(&encoded);
        let (status, response) = match response {
            Ok(result) => (result.status(), result),
            Err(ureq::Error::Status(code, result)) => (code, result),
            Err(ureq::Error::Transport(_)) => return Err(AiError::Transport),
        };
        if !(200..300).contains(&status) {
            return Ok((status, Value::Null));
        }
        use std::io::Read;
        let mut bytes = Vec::new();
        response
            .into_reader()
            .take(8_000_001)
            .read_to_end(&mut bytes)
            .map_err(|_| AiError::Transport)?;
        if bytes.len() > 8_000_000 {
            return Err(AiError::Invalid);
        }
        let value = serde_json::from_slice(&bytes).map_err(|_| AiError::Invalid)?;
        Ok((status, value))
    }
}

/// Decode complete SSE byte chunks with UTF-8 and event/total size limits.
/// Returns normalized JSON events; a missing terminal event is rejected.
pub fn parse_sse(chunks: &[&[u8]]) -> Result<Vec<Value>, AiError> {
    let mut bytes = Vec::new();
    for chunk in chunks {
        if bytes.len().saturating_add(chunk.len()) > 8_000_000 {
            return Err(AiError::Invalid);
        }
        bytes.extend_from_slice(chunk);
    }
    let content = std::str::from_utf8(&bytes).map_err(|_| AiError::Invalid)?;
    let normalized = content.replace("\r\n", "\n");
    let mut events = Vec::new();
    let mut finished = false;
    for block in normalized.split("\n\n") {
        if block.is_empty() {
            continue;
        }
        if block.len() > 262_144 {
            return Err(AiError::Invalid);
        }
        let data = block
            .lines()
            .filter_map(|line| line.strip_prefix("data:"))
            .map(str::trim_start)
            .collect::<Vec<_>>()
            .join("\n");
        if data.is_empty() {
            continue;
        }
        if data == "[DONE]" {
            finished = true;
            break;
        }
        let value: Value = serde_json::from_str(&data).map_err(|_| AiError::Invalid)?;
        if !value.is_object() {
            return Err(AiError::Invalid);
        }
        events.push(value);
    }
    if !finished {
        return Err(AiError::Invalid);
    }
    Ok(events)
}

/// Provider SSE envelopes after complete receipt; not an incremental network stream.
/// Anthropic terminates with `message_stop`; Gemini streams a sequence of JSON candidates.
pub fn parse_hosted_sse(chunks: &[&[u8]], kind: ProviderKind) -> Result<Vec<Value>, AiError> {
    let mut bytes = Vec::new();
    for chunk in chunks {
        if bytes.len().saturating_add(chunk.len()) > 8_000_000 {
            return Err(AiError::Invalid);
        }
        bytes.extend_from_slice(chunk);
    }
    let input = std::str::from_utf8(&bytes).map_err(|_| AiError::Invalid)?;
    let normalized = input.replace("\r\n", "\n");
    let mut events = Vec::new();
    let mut terminated = false;
    for block in normalized.split("\n\n") {
        if block.is_empty() {
            continue;
        }
        if block.len() > 262_144 {
            return Err(AiError::Invalid);
        }
        let data = block
            .lines()
            .filter_map(|line| line.strip_prefix("data:"))
            .map(str::trim_start)
            .collect::<Vec<_>>()
            .join("\n");
        if data.is_empty() {
            continue;
        }
        if data == "[DONE]" {
            terminated = true;
            break;
        }
        let value: Value = serde_json::from_str(&data).map_err(|_| AiError::Invalid)?;
        if !value.is_object() {
            return Err(AiError::Invalid);
        }
        if matches!(kind, ProviderKind::Anthropic) && value["type"] == "message_stop" {
            terminated = true;
        }
        if matches!(kind, ProviderKind::Gemini)
            && value
                .pointer("/candidates/0/finishReason")
                .and_then(Value::as_str)
                .is_some()
        {
            terminated = true;
        }
        events.push(value);
    }
    if !terminated {
        return Err(AiError::Invalid);
    }
    Ok(events)
}

pub fn classify_status(status: u16) -> Result<(), AiError> {
    match status {
        200..=299 => Ok(()),
        429 => Err(AiError::RateLimited),
        500..=599 => Err(AiError::Unavailable),
        _ => Err(AiError::Transport),
    }
}

pub fn chat<T: Transport>(
    transport: &T,
    profile: &ProviderProfile,
    policy: EgressPolicy,
    messages: &Value,
    cancelled: &dyn Fn() -> bool,
) -> Result<Response, AiError> {
    chat_with_secrets(transport, profile, policy, messages, cancelled, &|_| None)
}

/// Resolves credentials only after the egress gate. The returned secret is never retained
/// in profiles, results, serialized messages, or error strings.
pub fn chat_with_secrets<T: Transport>(
    transport: &T,
    profile: &ProviderProfile,
    policy: EgressPolicy,
    messages: &Value,
    cancelled: &dyn Fn() -> bool,
    resolve_secret: &dyn Fn(&str) -> Option<String>,
) -> Result<Response, AiError> {
    policy.authorize(profile)?;
    if cancelled() {
        return Err(AiError::Cancelled);
    }
    let items = messages.as_array().ok_or(AiError::Invalid)?;
    if items.is_empty()
        || items.len() > 64
        || serde_json::to_vec(messages)
            .map_err(|_| AiError::Invalid)?
            .len()
            > 500_000
    {
        return Err(AiError::Invalid);
    }
    for m in items {
        if !matches!(
            m.get("role").and_then(Value::as_str),
            Some("system" | "user" | "assistant")
        ) || m.get("content").and_then(Value::as_str).is_none()
        {
            return Err(AiError::Invalid);
        }
    }
    let base = profile.endpoint.trim_end_matches('/');
    let mut headers: Vec<(&str, &str)> = Vec::new();
    let secret = match profile.credential_reference.as_deref() {
        Some(reference) => Some(
            resolve_secret(reference)
                .filter(|s| !s.is_empty() && !s.chars().any(|c| c.is_control()))
                .ok_or(AiError::Invalid)?,
        ),
        None => None,
    };
    if !profile.local && secret.is_none() {
        return Err(AiError::Invalid);
    }
    let authorization = secret.as_ref().map(|s| format!("Bearer {s}"));
    let (endpoint, body) = match profile.kind {
        ProviderKind::OpenAiCompatible => {
            if let Some(ref token) = authorization {
                headers.push(("Authorization", token));
            }
            (
                format!("{base}/chat/completions"),
                serde_json::json!({"model":profile.model,"messages":messages,"stream":false}),
            )
        }
        ProviderKind::Ollama => (
            format!("{base}/api/chat"),
            serde_json::json!({"model":profile.model,"messages":messages,"stream":false}),
        ),
        ProviderKind::Anthropic => {
            headers.push(("x-api-key", secret.as_deref().ok_or(AiError::Invalid)?));
            headers.push(("anthropic-version", "2023-06-01"));
            let system = items
                .iter()
                .filter(|m| m["role"] == "system")
                .filter_map(|m| m["content"].as_str())
                .collect::<Vec<_>>()
                .join("\n");
            let conversation: Vec<Value> = items
                .iter()
                .filter(|m| m["role"] != "system")
                .cloned()
                .collect();
            if conversation.is_empty() {
                return Err(AiError::Invalid);
            }
            let mut body = serde_json::json!({"model":profile.model,"max_tokens":1024,"messages":conversation});
            if !system.is_empty() {
                body["system"] = Value::String(system);
            }
            (format!("{base}/messages"), body)
        }
        ProviderKind::Gemini => {
            headers.push(("x-goog-api-key", secret.as_deref().ok_or(AiError::Invalid)?));
            let system = items
                .iter()
                .filter(|m| m["role"] == "system")
                .filter_map(|m| m["content"].as_str())
                .collect::<Vec<_>>()
                .join("\n");
            let contents: Vec<Value> = items.iter().filter(|m| m["role"] != "system").map(|m|serde_json::json!({"role":if m["role"] == "assistant" {"model"} else {"user"},"parts":[{"text":m["content"]}]})).collect();
            if contents.is_empty() {
                return Err(AiError::Invalid);
            }
            let mut body = serde_json::json!({"contents":contents,"generationConfig":{"maxOutputTokens":1024}});
            if !system.is_empty() {
                body["systemInstruction"] = serde_json::json!({"parts":[{"text":system}]});
            }
            (
                format!("{base}/models/{}:generateContent", profile.model),
                body,
            )
        }
    };
    let (status, raw) = transport.post_json_headers(&endpoint, &body, &headers)?;
    classify_status(status)?;
    if cancelled() {
        return Err(AiError::Cancelled);
    }
    if matches!(profile.kind, ProviderKind::Anthropic | ProviderKind::Gemini) {
        return normalize_hosted(profile, &raw);
    }
    let response = if matches!(profile.kind, ProviderKind::Ollama) {
        raw.get("message")
    } else {
        raw.pointer("/choices/0/message")
    }
    .ok_or(AiError::Invalid)?;
    let text = response
        .get("content")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_owned();
    let mut proposals = Vec::new();
    if let Some(calls) = response.get("tool_calls").and_then(Value::as_array) {
        if !profile.capabilities.tools {
            return Err(AiError::UnsupportedCapability);
        }
        for call in calls {
            let id = call
                .get("id")
                .and_then(Value::as_str)
                .ok_or(AiError::Invalid)?;
            let fun = call.get("function").ok_or(AiError::Invalid)?;
            let name = fun
                .get("name")
                .and_then(Value::as_str)
                .ok_or(AiError::Invalid)?;
            let args = fun.get("arguments").ok_or(AiError::Invalid)?;
            let parsed = if let Some(s) = args.as_str() {
                serde_json::from_str(s).map_err(|_| AiError::Invalid)?
            } else {
                args.clone()
            };
            if id.is_empty() || name.is_empty() || !parsed.is_object() {
                return Err(AiError::Invalid);
            }
            proposals.push(ToolProposal {
                call_id: id.into(),
                operation: name.into(),
                arguments: parsed,
            });
        }
    }
    let usage = raw.get("usage").map(|u| Usage {
        prompt_tokens: u.get("prompt_tokens").and_then(Value::as_u64),
        completion_tokens: u.get("completion_tokens").and_then(Value::as_u64),
        total_tokens: u.get("total_tokens").and_then(Value::as_u64),
    });
    Ok(Response {
        text,
        usage,
        proposals,
    })
}

fn normalize_hosted(profile: &ProviderProfile, raw: &Value) -> Result<Response, AiError> {
    let (parts, usage, input_key, output_key, total_key) = match profile.kind {
        ProviderKind::Anthropic => (
            raw.get("content")
                .and_then(Value::as_array)
                .ok_or(AiError::Invalid)?,
            raw.get("usage"),
            "input_tokens",
            "output_tokens",
            "",
        ),
        ProviderKind::Gemini => (
            raw.pointer("/candidates/0/content/parts")
                .and_then(Value::as_array)
                .ok_or(AiError::Invalid)?,
            raw.get("usageMetadata"),
            "promptTokenCount",
            "candidatesTokenCount",
            "totalTokenCount",
        ),
        _ => return Err(AiError::Invalid),
    };
    let mut text = String::new();
    let mut proposals = Vec::new();
    for (index, part) in parts.iter().enumerate() {
        if let Some(piece) = part.get("text").and_then(Value::as_str) {
            text.push_str(piece);
        }
        let call = if matches!(profile.kind, ProviderKind::Anthropic) && part["type"] == "tool_use"
        {
            Some((
                part.get("id").and_then(Value::as_str),
                part.get("name").and_then(Value::as_str),
                part.get("input"),
            ))
        } else {
            part.get("functionCall").map(|function| {
                (
                    function.get("id").and_then(Value::as_str),
                    function.get("name").and_then(Value::as_str),
                    function.get("args"),
                )
            })
        };
        if let Some((id, name, args)) = call {
            if !profile.capabilities.tools {
                return Err(AiError::UnsupportedCapability);
            }
            let name = name.filter(|n| !n.is_empty()).ok_or(AiError::Invalid)?;
            let arguments = args
                .filter(|a| a.is_object())
                .ok_or(AiError::Invalid)?
                .clone();
            proposals.push(ToolProposal {
                call_id: id
                    .map(str::to_owned)
                    .unwrap_or_else(|| format!("gemini-{index}")),
                operation: name.into(),
                arguments,
            });
        }
    }
    if text.len() > 4_000_000 || (text.is_empty() && proposals.is_empty()) {
        return Err(AiError::Invalid);
    }
    let prompt_tokens = usage.and_then(|u| u.get(input_key)).and_then(Value::as_u64);
    let completion_tokens = usage
        .and_then(|u| u.get(output_key))
        .and_then(Value::as_u64);
    let total_tokens = if total_key.is_empty() {
        prompt_tokens
            .zip(completion_tokens)
            .and_then(|(a, b)| a.checked_add(b))
    } else {
        usage.and_then(|u| u.get(total_key)).and_then(Value::as_u64)
    };
    Ok(Response {
        text,
        proposals,
        usage: usage.map(|_| Usage {
            prompt_tokens,
            completion_tokens,
            total_tokens,
        }),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{Read, Write},
        net::TcpListener,
        thread,
    };

    fn server(status: &str, payload: &str) -> String {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let endpoint = format!("http://{}/v1", listener.local_addr().unwrap());
        let response = format!("HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{payload}", payload.len());
        thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(std::time::Duration::from_secs(3)))
                .unwrap();
            let mut buffer = [0u8; 8192];
            let mut request = Vec::new();
            loop {
                let n = socket.read(&mut buffer).unwrap_or(0);
                if n == 0 {
                    break;
                }
                request.extend_from_slice(&buffer[..n]);
                if let Some(end) = request.windows(4).position(|v| v == b"\r\n\r\n") {
                    let header = String::from_utf8_lossy(&request[..end]).to_ascii_lowercase();
                    let content_length = header
                        .lines()
                        .find_map(|line| {
                            line.strip_prefix("content-length:")
                                .and_then(|n| n.trim().parse::<usize>().ok())
                        })
                        .unwrap_or(0);
                    if request.len() >= end + 4 + content_length {
                        break;
                    }
                }
            }
            socket.write_all(response.as_bytes()).unwrap();
        });
        endpoint
    }

    #[test]
    fn local_http_openai_and_ollama() {
        let native = NativeHttpTransport::new(std::time::Duration::from_secs(3)).unwrap();
        let mut openai = profile();
        openai.endpoint = server(
            "200 OK",
            r#"{"choices":[{"message":{"content":"سلام دنیا"}}],"usage":{"total_tokens":5}}"#,
        );
        let result = chat(
            &native,
            &openai,
            policy(),
            &serde_json::json!([{"role":"user","content":"hi"}]),
            &|| false,
        )
        .unwrap();
        assert_eq!(result.text, "سلام دنیا");
        assert_eq!(result.usage.unwrap().total_tokens, Some(5));
        let mut ollama = profile();
        ollama.kind = ProviderKind::Ollama;
        ollama.endpoint = server("200 OK", r#"{"message":{"content":"local result"}}"#);
        assert_eq!(
            chat(
                &native,
                &ollama,
                policy(),
                &serde_json::json!([{"role":"user","content":"hello"}]),
                &|| { false }
            )
            .unwrap()
            .text,
            "local result"
        );
    }

    #[test]
    fn local_http_maps_rate_limit_and_server_error() {
        let transport = NativeHttpTransport::new(std::time::Duration::from_secs(3)).unwrap();
        for (status, expected) in [
            ("429 Too Many Requests", AiError::RateLimited),
            ("503 Service Unavailable", AiError::Unavailable),
        ] {
            let mut p = profile();
            p.endpoint = server(status, "{}");
            assert_eq!(
                chat(
                    &transport,
                    &p,
                    policy(),
                    &serde_json::json!([{"role":"user","content":"hello"}]),
                    &|| false
                ),
                Err(expected)
            );
        }
    }

    #[test]
    fn sse_splits_unicode_and_rejects_truncation() {
        let events = parse_sse(&[
            b"data: {\"choices\":[{\"delta\":{\"content\":\"",
            "سلام".as_bytes(),
            b"\"}}]}\n\ndata: [DONE]\n\n",
        ])
        .unwrap();
        assert_eq!(events[0]["choices"][0]["delta"]["content"], "سلام");
        assert_eq!(
            parse_sse(&[b"data: {\"partial\":true}"]),
            Err(AiError::Invalid)
        );
    }
    struct Mock(u16, Value);
    impl Transport for Mock {
        fn post_json(&self, _: &str, _: &Value) -> Result<(u16, Value), AiError> {
            Ok((self.0, self.1.clone()))
        }
    }
    fn profile() -> ProviderProfile {
        ProviderProfile {
            id: "local".into(),
            kind: ProviderKind::OpenAiCompatible,
            model: "test".into(),
            endpoint: "http://127.0.0.1:8000/v1".into(),
            local: true,
            credential_reference: None,
            capabilities: Capabilities {
                streaming: true,
                tools: true,
                structured_output: false,
            },
        }
    }
    fn policy() -> EgressPolicy {
        EgressPolicy {
            offline: true,
            external_allowed: false,
        }
    }
    #[test]
    fn offline_denies_remote() {
        let mut p = profile();
        p.local = false;
        p.endpoint = "https://example.org/v1".into();
        assert_eq!(policy().authorize(&p), Err(AiError::Offline));
    }
    #[test]
    fn errors_are_classified() {
        assert_eq!(classify_status(429), Err(AiError::RateLimited));
        assert_eq!(classify_status(503), Err(AiError::Unavailable));
    }
    #[test]
    fn cancellation() {
        assert_eq!(
            chat(
                &Mock(200, serde_json::json!({})),
                &profile(),
                policy(),
                &serde_json::json!([{"role":"user","content":"hello"}]),
                &|| true
            ),
            Err(AiError::Cancelled)
        );
    }
    #[test]
    fn proposal_is_data_only() {
        let mock = Mock(
            200,
            serde_json::json!({"choices":[{"message":{"content":"","tool_calls":[{"id":"call","function":{"name":"project.delete","arguments":"{\"id\":1}"}}]}}]}),
        );
        let response = chat(
            &mock,
            &profile(),
            policy(),
            &serde_json::json!([{"role":"user","content":"hello"}]),
            &|| false,
        )
        .unwrap();
        assert_eq!(response.proposals[0].operation, "project.delete");
        let mut p = profile();
        p.capabilities.tools = false;
        assert_eq!(
            chat(
                &mock,
                &p,
                policy(),
                &serde_json::json!([{"role":"user","content":"hello"}]),
                &|| false
            ),
            Err(AiError::UnsupportedCapability)
        );
    }

    #[test]
    fn hosted_mock_http_headers_body_usage_and_proposals() {
        use std::sync::mpsc;
        let native = NativeHttpTransport::new(std::time::Duration::from_secs(3)).unwrap();
        for kind in [
            ProviderKind::Anthropic,
            ProviderKind::Gemini,
            ProviderKind::OpenAiCompatible,
        ] {
            let listener = TcpListener::bind("127.0.0.1:0").unwrap();
            let base = format!("http://{}/v1", listener.local_addr().unwrap());
            let (tx, rx) = mpsc::channel();
            let expected_kind = kind.clone();
            let payload = match kind {
                ProviderKind::Anthropic => serde_json::json!({"content":[{"type":"text","text":"سلام 🌍"},{"type":"tool_use","id":"tool-1","name":"search","input":{"q":"x"}}],"usage":{"input_tokens":2,"output_tokens":3}}),
                ProviderKind::Gemini => serde_json::json!({"candidates":[{"content":{"parts":[{"text":"سلام 🌍"},{"functionCall":{"name":"search","args":{"q":"x"}}}]}}],"usageMetadata":{"promptTokenCount":2,"candidatesTokenCount":3,"totalTokenCount":5}}),
                _ => serde_json::json!({"choices":[{"message":{"content":"سلام 🌍"}}]}),
            }.to_string();
            thread::spawn(move || {
                let (mut socket, _) = listener.accept().unwrap();
                socket
                    .set_read_timeout(Some(std::time::Duration::from_secs(3)))
                    .unwrap();
                let mut request = Vec::new();
                let mut buf = [0; 4096];
                loop {
                    let n = socket.read(&mut buf).unwrap();
                    if n == 0 {
                        break;
                    }
                    request.extend_from_slice(&buf[..n]);
                    if let Some(end) = request.windows(4).position(|x| x == b"\r\n\r\n") {
                        let headers = String::from_utf8_lossy(&request[..end]).to_ascii_lowercase();
                        let len = headers
                            .lines()
                            .find_map(|s| s.strip_prefix("content-length:"))
                            .and_then(|s| s.trim().parse::<usize>().ok())
                            .unwrap_or(0);
                        if request.len() >= end + 4 + len {
                            break;
                        }
                    }
                }
                tx.send(String::from_utf8(request).unwrap()).unwrap();
                let response = format!("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{payload}",payload.len());
                socket.write_all(response.as_bytes()).unwrap();
            });
            let mut p = profile();
            p.kind = kind;
            p.endpoint = base;
            p.local = matches!(p.kind, ProviderKind::OpenAiCompatible);
            p.credential_reference = Some("vault-key".into());
            let allowed = EgressPolicy {
                offline: false,
                external_allowed: true,
            };
            let result = chat_with_secrets(&native,&p,allowed,&serde_json::json!([{"role":"system","content":"safe"},{"role":"user","content":"hi"}]),&||false,&|reference| {assert_eq!(reference,"vault-key");Some("secret-token".into())}).unwrap();
            assert_eq!(result.text, "سلام 🌍");
            let captured = rx.recv().unwrap();
            assert!(captured.contains("secret-token"));
            match expected_kind {
                ProviderKind::Anthropic => {
                    assert!(captured.contains("POST /v1/messages"));
                    assert!(captured.contains("x-api-key: secret-token"));
                    assert!(captured.contains("\"system\":\"safe\""));
                    assert_eq!(result.proposals.len(), 1);
                }
                ProviderKind::Gemini => {
                    assert!(captured.contains("/models/test:generateContent"));
                    assert!(captured.contains("x-goog-api-key: secret-token"));
                    assert!(captured.contains("systemInstruction"));
                    assert_eq!(result.proposals.len(), 1);
                }
                ProviderKind::OpenAiCompatible => {
                    assert!(
                        captured.contains("authorization: Bearer secret-token")
                            || captured.contains("Authorization: Bearer secret-token")
                    );
                }
                _ => unreachable!(),
            }
        }
    }

    #[test]
    fn hosted_stream_envelopes_split_unicode() {
        let body = "event: content_block_delta\ndata: {\"type\":\"content_block_delta\",\"delta\":{\"text\":\"سلام\"}}\n\nevent: message_stop\ndata: {\"type\":\"message_stop\"}\n\n";
        let bytes = body.as_bytes();
        let split = body.find('س').unwrap() + 1;
        let parsed =
            parse_hosted_sse(&[&bytes[..split], &bytes[split..]], ProviderKind::Anthropic).unwrap();
        assert_eq!(parsed[0]["delta"]["text"], "سلام");
        assert_eq!(
            parse_hosted_sse(&[&bytes[..split]], ProviderKind::Anthropic),
            Err(AiError::Invalid)
        );
        let gemini = b"data: {\"candidates\":[{\"finishReason\":\"STOP\"}]}\n\n";
        assert_eq!(
            parse_hosted_sse(&[gemini], ProviderKind::Gemini)
                .unwrap()
                .len(),
            1
        );
    }

    #[test]
    fn remote_denial_precedes_secret_resolution_and_transport() {
        let mut p = profile();
        p.kind = ProviderKind::Anthropic;
        p.local = false;
        p.endpoint = "https://api.anthropic.com/v1".into();
        p.credential_reference = Some("runtime-secret".into());
        let result = chat_with_secrets(
            &Mock(200, Value::Null),
            &p,
            policy(),
            &serde_json::json!([{"role":"user","content":"hello"}]),
            &|| false,
            &|_| panic!("offline egress must not resolve credentials"),
        );
        assert_eq!(result, Err(AiError::Offline));
    }
}
