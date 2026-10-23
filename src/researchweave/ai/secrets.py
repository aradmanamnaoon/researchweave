"""OS credential-store integration without project-local plaintext secrets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from .errors import AIError


class CredentialBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


@dataclass(frozen=True)
class SecretReference:
    """Opaque credential locator safe for configuration and exports."""

    provider: str
    profile: str
    scheme: str = "os-keyring-v1"


class KeyringSecretStore:
    """Credentials remain in OS-protected storage, never in project SQLite.

    The constructor does not load secrets or probe backends. The host authorizes
    set/delete before calling this adapter; read returns a plaintext string
    exclusively to the caller's in-memory provider transport.
    """

    def __init__(self, backend: CredentialBackend | None = None) -> None:
        if backend is None:
            try:
                import keyring
            except ImportError as exc:
                raise AIError(
                    "DEPENDENCY_MISSING", "Install optional OS keyring integration"
                ) from exc
            backend = keyring.get_keyring()
        self.backend = backend

    @staticmethod
    def _validate(provider: str, profile: str) -> None:
        pattern = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
        if not pattern.fullmatch(provider) or not pattern.fullmatch(profile):
            raise AIError("INVALID_INPUT", "Invalid provider or credential profile name")

    def _key(self, reference: SecretReference) -> tuple[str, str]:
        if reference.scheme != "os-keyring-v1":
            raise AIError("UNSUPPORTED_FORMAT", "Unsupported secret reference scheme")
        self._validate(reference.provider, reference.profile)
        return (f"researchweave.provider.{reference.provider}", reference.profile)

    def store(self, provider: str, profile: str, value: str) -> SecretReference:
        self._validate(provider, profile)
        if not value or len(value) > 32_768:
            raise AIError("INVALID_INPUT", "Invalid secret length")
        reference = SecretReference(provider, profile)
        service, username = self._key(reference)
        try:
            self.backend.set_password(service, username, value)
        except Exception as exc:
            raise AIError("PROVIDER_UNAVAILABLE", "Operating-system keyring write failed") from exc
        return reference

    def resolve(self, reference: SecretReference) -> str:
        service, username = self._key(reference)
        try:
            secret = self.backend.get_password(service, username)
        except Exception as exc:
            raise AIError("PROVIDER_UNAVAILABLE", "Operating-system keyring read failed") from exc
        if secret is None:
            raise AIError("NOT_FOUND", "Provider credential is missing from OS keyring")
        return secret

    def delete(self, reference: SecretReference) -> None:
        service, username = self._key(reference)
        try:
            self.backend.delete_password(service, username)
        except Exception as exc:
            raise AIError("PROVIDER_UNAVAILABLE", "Operating-system keyring delete failed") from exc
