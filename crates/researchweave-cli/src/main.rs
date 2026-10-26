use researchweave_ai::profile_store::ProfileStore;
use researchweave_ai::{
    agent_actions::AgentActionStore,
    conversations::ConversationStore,
    grounding::GroundingStore,
    operations::{capabilities as ai_capabilities, AiOperationHandler, NoSecrets},
    prompts::PromptStore,
    EgressPolicy, NativeHttpTransport,
};
use researchweave_analysis::AnalysisService;
use researchweave_cloud::{CloudOperationHandler, OsKeyringStore, OsSyncSecretStore};
use researchweave_core::{AuditStore, Authority, CommandRouter};
use researchweave_evidence::EvidenceHandler;
use researchweave_library::LibraryHandler;
use researchweave_project::ProjectHandler;
use serde_json::{json, Value};
use std::{
    env, fs,
    path::{Path, PathBuf},
    sync::Arc,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Subcommand {
    Health,
    Capabilities,
    UpdateCheck,
}

#[derive(Debug)]
struct Args {
    data_dir: PathBuf,
    command: Subcommand,
}

fn usage() -> &'static str {
    "Usage: researchweave-cli [--data-dir PATH] <health|capabilities|update-check>"
}

fn parse_args<I>(args: I) -> Result<Args, String>
where
    I: IntoIterator<Item = String>,
{
    let mut data_dir = env::var_os("RESEARCHWEAVE_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(".researchweave-data"));
    let mut command = None;
    let mut iter = args.into_iter();
    while let Some(arg) = iter.next() {
        match arg.as_str() {
            "--data-dir" => {
                let value = iter
                    .next()
                    .ok_or_else(|| "--data-dir requires a path".to_owned())?;
                data_dir = PathBuf::from(value);
            }
            "health" => {
                if command.replace(Subcommand::Health).is_some() {
                    return Err("only one subcommand may be supplied".into());
                }
            }
            "capabilities" => {
                if command.replace(Subcommand::Capabilities).is_some() {
                    return Err("only one subcommand may be supplied".into());
                }
            }
            "update-check" => {
                if command.replace(Subcommand::UpdateCheck).is_some() {
                    return Err("only one subcommand may be supplied".into());
                }
            }
            "-h" | "--help" => return Err(usage().into()),
            _ if arg.starts_with("--data-dir=") => {
                let value = arg.trim_start_matches("--data-dir=");
                if value.is_empty() {
                    return Err("--data-dir requires a path".into());
                }
                data_dir = PathBuf::from(value);
            }
            _ => return Err(format!("unknown argument: {arg}")),
        }
    }
    Ok(Args {
        data_dir,
        command: command.ok_or_else(|| "a subcommand is required".to_owned())?,
    })
}

struct Services {
    router: CommandRouter,
    agent_actions: Arc<AgentActionStore>,
    #[cfg(test)]
    authority: Arc<Authority>,
}

impl Services {
    fn build(root: &Path) -> Result<Self, String> {
        fs::create_dir_all(root).map_err(|error| error.to_string())?;
        let evidence = root.join("evidence");
        let analysis = root.join("analysis");
        let imports = root.join("imports");
        fs::create_dir_all(&evidence).map_err(|error| error.to_string())?;
        fs::create_dir_all(&analysis).map_err(|error| error.to_string())?;
        fs::create_dir_all(&imports).map_err(|error| error.to_string())?;

        let authority = Arc::new(Authority::new());
        let audit = Arc::new(
            AuditStore::open(root.join("integration-audit.sqlite"))
                .map_err(|error| error.to_string())?,
        );
        let mut router = CommandRouter::new(Arc::clone(&authority), audit);

        let project_handler = Arc::new(ProjectHandler::new(&evidence));
        router
            .register("project", project_handler, ProjectHandler::capabilities())
            .map_err(|error| error.to_string())?;

        let evidence_handler = Arc::new(EvidenceHandler::new(evidence.clone()));
        router
            .register(
                "evidence",
                evidence_handler,
                EvidenceHandler::capabilities(),
            )
            .map_err(|error| error.to_string())?;

        let library_handler = Arc::new(LibraryHandler::new(evidence.clone()));
        router
            .register("library", library_handler, LibraryHandler::capabilities())
            .map_err(|error| error.to_string())?;

        let analysis_handler =
            Arc::new(AnalysisService::new(analysis, imports).map_err(|error| error.to_string())?);
        router
            .register(
                "analysis",
                analysis_handler,
                AnalysisService::capabilities(),
            )
            .map_err(|error| error.to_string())?;

        let cloud_handler = Arc::new(
            CloudOperationHandler::with_profile_path(
                Arc::new(OsKeyringStore),
                Arc::new(OsSyncSecretStore),
                root.join("cloud-profiles.json"),
            )
            .map_err(|error| error.to_string())?,
        );
        router
            .register(
                "cloud",
                cloud_handler,
                CloudOperationHandler::capabilities(),
            )
            .map_err(|error| error.to_string())?;

        let ai_transport = NativeHttpTransport::new(std::time::Duration::from_secs(25))
            .map_err(|error| error.to_string())?;
        let conversations = Arc::new(
            ConversationStore::open(&root.join("ai-conversations.json"))
                .map_err(|error| error.to_string())?,
        );
        let prompts = Arc::new(
            PromptStore::open(&root.join("ai-prompts.json")).map_err(|error| error.to_string())?,
        );
        let grounding = Arc::new(
            GroundingStore::open(&root.join("ai-grounding.json"))
                .map_err(|error| error.to_string())?,
        );
        let agent_actions = Arc::new(
            AgentActionStore::open(&root.join("ai-agent-actions.json"))
                .map_err(|error| error.to_string())?,
        );
        let ai_handler = Arc::new(
            AiOperationHandler::new(
                ai_transport,
                Arc::new(NoSecrets),
                EgressPolicy {
                    offline: true,
                    external_allowed: false,
                },
            )
            .with_conversations(conversations)
            .with_prompts(prompts)
            .with_grounding(grounding)
            .with_profiles(Arc::new(
                ProfileStore::open(&root.join("ai-profiles.json")).map_err(|e| e.to_string())?,
            )),
        );
        router
            .register("ai", ai_handler, ai_capabilities())
            .map_err(|error| error.to_string())?;

        Ok(Self {
            router,
            agent_actions,
            #[cfg(test)]
            authority,
        })
    }

    fn health(&self) -> Value {
        let capabilities = self.router.capabilities();
        let agent_action_store_attached = Arc::strong_count(&self.agent_actions) >= 1;
        let count = |domain: &str| {
            capabilities
                .iter()
                .filter(|item| item.get("domain").and_then(Value::as_str) == Some(domain))
                .count()
        };
        json!({
            "status": "ok",
            "offline": true,
            "domains": {
                "project": {"status":"ok","operations":count("project")},
                "evidence": {"status":"ok","operations":count("evidence")},
                "library": {"status":"ok","operations":count("library")},
                "analysis": {"status":"ok","operations":count("analysis")},
                "ai": {"status":"implemented","registered_operations":count("ai"),"transport":"native-rust","offline_default":true,"durable_agent_action_store":agent_action_store_attached},
                "cloud": {"status":"implemented","registered_operations":count("cloud"),"safe_sync_requires_live_conditional_write_probe":true},
                "desktop": {"status":"implemented","registered_operations":0,"gui_framework":"slint"}
            },
            "operations": capabilities.len()
        })
    }
}

fn run(args: Args) -> Result<Value, String> {
    match args.command {
        Subcommand::UpdateCheck => update_check(),
        Subcommand::Health | Subcommand::Capabilities => {
            let services = Services::build(&args.data_dir)?;
            Ok(match args.command {
                Subcommand::Health => services.health(),
                Subcommand::Capabilities => Value::Array(services.router.capabilities()),
                Subcommand::UpdateCheck => unreachable!(),
            })
        }
    }
}

const UPDATE_ENDPOINT: &str =
    "https://api.github.com/repos/aradmanamnaoon/researchweave/releases/latest";

fn parse_three_component_version(value: &str) -> Result<[u64; 3], String> {
    let value = value.strip_prefix('v').unwrap_or(value);
    let parts: Vec<&str> = value.split('.').collect();
    if parts.len() != 3
        || parts
            .iter()
            .any(|part| part.is_empty() || !part.bytes().all(|byte| byte.is_ascii_digit()))
    {
        return Err("release tag is not a three-component stable version".into());
    }
    let mut parsed = [0_u64; 3];
    for (index, part) in parts.into_iter().enumerate() {
        parsed[index] = part
            .parse::<u64>()
            .map_err(|_| "release version component is out of range".to_owned())?;
    }
    Ok(parsed)
}

fn update_result_from_release(value: &Value) -> Result<Value, String> {
    let tag = value
        .get("tag_name")
        .and_then(Value::as_str)
        .ok_or_else(|| "release response is missing tag_name".to_owned())?;
    let release_url = value
        .get("html_url")
        .and_then(Value::as_str)
        .filter(|url| url.starts_with("https://github.com/aradmanamnaoon/researchweave/releases/"))
        .ok_or_else(|| "release response contains an unexpected release URL".to_owned())?;
    if value.get("draft").and_then(Value::as_bool).unwrap_or(false)
        || value
            .get("prerelease")
            .and_then(Value::as_bool)
            .unwrap_or(false)
    {
        return Err("latest release response is not a stable published release".into());
    }
    let latest = parse_three_component_version(tag)?;
    let current_text = env!("CARGO_PKG_VERSION");
    let current = parse_three_component_version(current_text)?;
    Ok(json!({
        "status":"ok",
        "current_version":current_text,
        "latest_version":tag.strip_prefix('v').unwrap_or(tag),
        "update_available":latest > current,
        "release_url":release_url,
        "source":"github-releases",
        "endpoint":UPDATE_ENDPOINT,
        "automatic_download":false,
        "automatic_install":false
    }))
}

fn update_check() -> Result<Value, String> {
    let agent = ureq::AgentBuilder::new()
        .timeout_connect(std::time::Duration::from_secs(5))
        .timeout_read(std::time::Duration::from_secs(10))
        .timeout_write(std::time::Duration::from_secs(10))
        .redirects(0)
        .build();
    let response = agent
        .get(UPDATE_ENDPOINT)
        .set(
            "User-Agent",
            concat!("ResearchWeave/", env!("CARGO_PKG_VERSION")),
        )
        .set("Accept", "application/vnd.github+json")
        .call()
        .map_err(|error| format!("update check failed: {error}"))?;
    let content_type = response
        .header("Content-Type")
        .unwrap_or_default()
        .to_ascii_lowercase();
    if !content_type.contains("application/json") {
        return Err("update endpoint returned a non-JSON response".into());
    }
    let value: Value = response
        .into_json()
        .map_err(|_| "update endpoint returned invalid JSON".to_owned())?;
    update_result_from_release(&value)
}

fn main() {
    let result = parse_args(env::args().skip(1)).and_then(run);
    match result {
        Ok(value) => match serde_json::to_string_pretty(&value) {
            Ok(text) => println!("{text}"),
            Err(error) => {
                eprintln!("researchweave-cli: {error}");
                std::process::exit(1);
            }
        },
        Err(error) => {
            eprintln!("researchweave-cli: {error}");
            eprintln!("{}", usage());
            std::process::exit(2);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parser_requires_exact_subcommand_and_supports_unicode_path() {
        let args = parse_args([
            "--data-dir".to_owned(),
            "پژوهش".to_owned(),
            "health".to_owned(),
        ])
        .unwrap();
        assert_eq!(args.data_dir, PathBuf::from("پژوهش"));
        assert_eq!(args.command, Subcommand::Health);
        assert!(parse_args(["unknown".to_owned()]).is_err());
        assert!(parse_args(["health".to_owned(), "capabilities".to_owned()]).is_err());
        assert_eq!(
            parse_args(["update-check".to_owned()]).unwrap().command,
            Subcommand::UpdateCheck
        );
    }

    #[test]
    fn update_response_is_stable_read_only_and_fail_closed() {
        let newer = update_result_from_release(&json!({
            "tag_name":"v99.2.3",
            "html_url":"https://github.com/aradmanamnaoon/researchweave/releases/tag/v99.2.3",
            "draft":false,
            "prerelease":false
        }))
        .unwrap();
        assert_eq!(newer["update_available"], true);
        assert_eq!(newer["automatic_download"], false);
        assert_eq!(newer["automatic_install"], false);
        assert_eq!(newer["source"], "github-releases");
        assert!(update_result_from_release(&json!({
            "tag_name":"v1.2.3-beta",
            "html_url":"https://github.com/aradmanamnaoon/researchweave/releases/tag/v1.2.3-beta",
            "draft":false,
            "prerelease":true
        }))
        .is_err());
        assert!(update_result_from_release(&json!({
            "tag_name":"v1.2.3",
            "html_url":"https://example.invalid/releases/tag/v1.2.3",
            "draft":false,
            "prerelease":false
        }))
        .is_err());
        assert!(parse_three_component_version("v1.2").is_err());
        assert!(parse_three_component_version("1.2.3.4").is_err());
    }

    #[test]
    fn health_and_capabilities_use_same_native_router() {
        let dir = tempfile::tempdir().unwrap();
        let services = Services::build(dir.path()).unwrap();
        let health = services.health();
        let capabilities = services.router.capabilities();
        assert_eq!(health["status"], "ok");
        assert_eq!(health["offline"], true);
        assert_eq!(health["domains"]["ai"]["durable_agent_action_store"], true);
        assert_eq!(
            health["operations"].as_u64().unwrap() as usize,
            capabilities.len()
        );
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "dataset.import"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "question.feedback"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "search.query"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "project.timeline"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "cloud.conditional.probe"
                && item["effect"] == "external-network"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "cloud.credentials.store"
                && item["effect"] == "local-write"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "cloud.sync.tip"
                && item["effect"] == "external-network"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "cloud.sync.history"
                && item["effect"] == "external-network"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "ai.profile.validate" && item["effect"] == "read"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "ai.chat.propose"
                && item["effect"] == "external-network"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "assistant.conversation.create"
                && item["effect"] == "local-write"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "assistant.history" && item["effect"] == "read"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "prompt.add" && item["effect"] == "local-write"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "prompt.render" && item["effect"] == "read"));
        assert!(capabilities.iter().any(|item| {
            item["operation"] == "assistant.retrieval.index" && item["effect"] == "local-write"
        }));
        assert!(capabilities.iter().any(|item| {
            item["operation"] == "assistant.retrieval.search" && item["effect"] == "read"
        }));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "assistant.agent.plan" && item["effect"] == "read"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "cloud.sync.push"
                && item["effect"] == "external-network"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "cloud.sync.pull"
                && item["effect"] == "external-network"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "project.archive" && item["effect"] == "local-write"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "writing.section_save"
                && item["effect"] == "local-write"));
        assert!(capabilities
            .iter()
            .any(|item| item["operation"] == "project.create" && item["effect"] == "local-write"));
        assert_eq!(
            capabilities
                .iter()
                .filter(|item| item["operation"] == "project.open")
                .count(),
            1
        );
        assert!(capabilities.iter().all(|item| item.get("effect").is_some()));

        let project_id = "11111111-1111-4111-8111-111111111111".parse().unwrap();
        let retrieval = services
            .router
            .dispatch(
                &researchweave_core::Command::new(
                    project_id,
                    "assistant.retrieval.search",
                    json!({"query":"neurons","limit":5,"byte_budget":1024}),
                ),
                None,
                1.0,
            )
            .unwrap();
        assert_eq!(retrieval["status"], "ok", "{retrieval}");
        assert_eq!(retrieval["data"]["results"], json!([]));
        assert_eq!(retrieval["data"]["no_external_search"], true);
    }

    #[test]
    fn production_host_agent_action_executes_exact_router_command_and_restarts() {
        let dir = tempfile::tempdir().unwrap();
        let project_id = "33333333-3333-4333-8333-333333333333";
        let project = project_id.parse().unwrap();
        let services = Services::build(dir.path()).unwrap();
        let mut command = researchweave_core::Command::new(
            project,
            "assistant.retrieval.index",
            json!({
                "citation_id":"agent-citation",
                "source_id":"agent-source",
                "revision":"r1",
                "content":"Private project evidence retained locally."
            }),
        );
        command.actor = "researchweave-ai-agent".into();
        let proposed = services
            .agent_actions
            .propose(&services.router, command)
            .unwrap();
        assert_eq!(proposed.state, "proposed");
        assert!(services
            .agent_actions
            .approve(project_id, &proposed.id, &"0".repeat(64))
            .is_err());
        let approved = services
            .agent_actions
            .approve(project_id, &proposed.id, &proposed.fingerprint)
            .unwrap();
        assert_eq!(approved.state, "approved");
        let executed = services
            .agent_actions
            .execute(project_id, &proposed.id, &services.router, 10.0)
            .unwrap();
        assert_eq!(executed["status"], "ok", "{executed}");

        let search = services
            .router
            .dispatch(
                &researchweave_core::Command::new(
                    project,
                    "assistant.retrieval.search",
                    json!({"query":"private evidence","limit":5,"byte_budget":2048}),
                ),
                None,
                11.0,
            )
            .unwrap();
        assert_eq!(search["data"]["results"].as_array().unwrap().len(), 1);

        let mut denied_command = researchweave_core::Command::new(
            project,
            "assistant.retrieval.revoke_source",
            json!({"source_id":"agent-source"}),
        );
        denied_command.actor = "researchweave-ai-agent".into();
        let denied_proposal = services
            .agent_actions
            .propose(&services.router, denied_command)
            .unwrap();
        let denied = services
            .agent_actions
            .deny(
                project_id,
                &denied_proposal.id,
                &denied_proposal.fingerprint,
                "Keep this source.",
            )
            .unwrap();
        assert_eq!(denied.state, "denied");
        assert!(services
            .agent_actions
            .execute(project_id, &denied_proposal.id, &services.router, 12.0)
            .is_err());
        drop(services);

        let reopened = Services::build(dir.path()).unwrap();
        let timeline = reopened.agent_actions.timeline(project_id).unwrap();
        assert_eq!(timeline.len(), 2);
        assert!(timeline.iter().any(|item| item.state == "completed"));
        assert!(timeline.iter().any(|item| item.state == "denied"));
        let search_after_restart = reopened
            .router
            .dispatch(
                &researchweave_core::Command::new(
                    project,
                    "assistant.retrieval.search",
                    json!({"query":"private evidence","limit":5,"byte_budget":2048}),
                ),
                None,
                13.0,
            )
            .unwrap();
        assert_eq!(
            search_after_restart["data"]["results"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        let audit = AuditStore::open(dir.path().join("integration-audit.sqlite")).unwrap();
        let agent_events: Vec<_> = audit
            .events()
            .unwrap()
            .into_iter()
            .filter(|event| event.actor == "researchweave-ai-agent")
            .collect();
        assert_eq!(agent_events.len(), 1);
        assert_eq!(agent_events[0].operation, "assistant.retrieval.index");
        assert_eq!(agent_events[0].effect, "local-write");
        assert!(!serde_json::to_string(&agent_events)
            .unwrap()
            .contains("Private project evidence"));
    }

    #[test]
    fn ai_profile_router_requires_approval_and_reopens_redacted_metadata() {
        let root = tempfile::tempdir().unwrap();
        let project = "55555555-5555-4555-8555-555555555555".parse().unwrap();
        let host = Services::build(root.path()).unwrap();
        let profile = json!({"id":"provider-one","kind":"open_ai_compatible",
            "model":"test-model","endpoint":"https://example.org/v1","local":false,
            "capabilities":{"streaming":false,"tools":false,"structured_output":false}});
        let command = researchweave_core::Command::new(
            project,
            "ai.profile.configure",
            json!({"id":"provider-one","profile":profile}),
        );
        let denied = host.router.dispatch(&command, None, 1.0);
        assert!(denied.is_err() || denied.as_ref().is_ok_and(|value| value["status"] != "ok"));
        let empty = host
            .router
            .dispatch(
                &researchweave_core::Command::new(project, "ai.profile.list", json!({})),
                None,
                2.0,
            )
            .unwrap();
        assert_eq!(empty["data"]["providers"], json!([]));
        let approval = host.authority.issue(&command, 30, 3.0).unwrap();
        assert_eq!(
            host.router
                .dispatch(&command, Some(&approval), 4.0)
                .unwrap()["status"],
            "ok"
        );
        drop(host);
        let reopened = Services::build(root.path()).unwrap();
        let listed = reopened
            .router
            .dispatch(
                &researchweave_core::Command::new(project, "ai.profile.list", json!({})),
                None,
                4.0,
            )
            .unwrap();
        assert_eq!(listed["data"]["providers"][0]["model"], "test-model");
        let serialized = serde_json::to_string(&listed).unwrap();
        assert!(!serialized.contains("endpoint"));
        assert!(!serialized.contains("credential"));
        let file = std::fs::read_to_string(root.path().join("ai-profiles.json")).unwrap();
        assert!(!file.contains("credential_reference"));
        assert!(!file.contains("api_key"));
        let audit = AuditStore::open(root.path().join("integration-audit.sqlite")).unwrap();
        assert!(!audit.events().unwrap().is_empty());
    }
}
