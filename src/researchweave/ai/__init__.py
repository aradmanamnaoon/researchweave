"""Local-first, host-controlled AI integration domain."""

from .external_connectors import ConnectorRegistry
from .facade import AIFacade, build_ai_facade
from .policy import EgressPolicy
from .provider_services import ProviderCatalog
from .providers import ProviderProfile, ProviderRegistry
from .remote_sync import EncryptedRemoteSync

__all__ = [
    "AIFacade",
    "ConnectorRegistry",
    "EgressPolicy",
    "EncryptedRemoteSync",
    "ProviderCatalog",
    "ProviderProfile",
    "ProviderRegistry",
    "build_ai_facade",
]
