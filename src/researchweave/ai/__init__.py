"""Local-first, host-controlled AI integration domain."""

from .facade import AIFacade, build_ai_facade
from .policy import EgressPolicy
from .providers import ProviderProfile, ProviderRegistry

__all__ = ["AIFacade", "EgressPolicy", "ProviderProfile", "ProviderRegistry", "build_ai_facade"]
