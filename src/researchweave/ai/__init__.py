"""Local-first, host-controlled AI integration domain."""

from .conversations import ConversationMessage, ConversationStore
from .external_connectors import ConnectorRegistry
from .facade import AIFacade, build_ai_facade
from .interactive_agent import AgentLoopResult, AgentToolEvent, ModelAgentLoop
from .model_runtime import ConfiguredModelRuntime, ModelConfigStore, ModelProfile
from .policy import EgressPolicy
from .provider_services import ProviderCatalog
from .providers import ProviderProfile, ProviderRegistry
from .remote_sync import EncryptedRemoteSync

__all__ = [
    "AIFacade",
    "AgentLoopResult",
    "AgentToolEvent",
    "ConnectorRegistry",
    "ConversationMessage",
    "ConversationStore",
    "EgressPolicy",
    "EncryptedRemoteSync",
    "ConfiguredModelRuntime",
    "ModelConfigStore",
    "ModelProfile",
    "ModelAgentLoop",
    "ProviderCatalog",
    "ProviderProfile",
    "ProviderRegistry",
    "build_ai_facade",
]
