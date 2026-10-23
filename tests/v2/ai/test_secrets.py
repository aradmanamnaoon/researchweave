from __future__ import annotations

import pytest

from researchweave.ai.errors import AIError
from researchweave.ai.secrets import KeyringSecretStore, SecretReference


class MemoryKeyring:
    def __init__(self):
        self.items = {}

    def get_password(self, service, username):
        return self.items.get((service, username))

    def set_password(self, service, username, password):
        self.items[(service, username)] = password

    def delete_password(self, service, username):
        del self.items[(service, username)]


def test_opaque_keyring_reference_roundtrip_and_delete():
    fake = MemoryKeyring()
    store = KeyringSecretStore(fake)
    ref = store.store("provider", "personal", "THIS-IS-A-SYNTHETIC-CREDENTIAL")
    assert ref == SecretReference("provider", "personal")
    assert "SYNTHETIC-CREDENTIAL" not in repr(ref)
    assert store.resolve(ref) == "THIS-IS-A-SYNTHETIC-CREDENTIAL"
    assert fake.items[("researchweave.provider.provider", "personal")]
    store.delete(ref)
    with pytest.raises(AIError) as error:
        store.resolve(ref)
    assert error.value.code == "NOT_FOUND"


@pytest.mark.parametrize("provider,profile", [("../admin", "p"), ("ok", ""), ("", "good")])
def test_invalid_secret_reference_denied(provider, profile):
    store = KeyringSecretStore(MemoryKeyring())
    with pytest.raises(AIError) as error:
        store.store(provider, profile, "value")
    assert error.value.code == "INVALID_INPUT"


def test_unsupported_keyring_scheme_rejected():
    store = KeyringSecretStore(MemoryKeyring())
    with pytest.raises(AIError) as error:
        store.resolve(SecretReference("provider", "p", "plaintext-config"))
    assert error.value.code == "UNSUPPORTED_FORMAT"
