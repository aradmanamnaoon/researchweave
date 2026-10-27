# §40.86 — durable AI provider metadata (backend slice)

The production CLI now attaches a bounded `ProfileStore` at
`<data-root>/ai-profiles.json`. It accepts a strict version-1 JSON schema and
up to 64 unique provider profiles. Each profile includes only identifier,
provider kind, model, endpoint, local flag and declared model capabilities.
Provider validation reuses `ProviderProfile::validate`. Unknown fields,
credential references, raw API keys, duplicate IDs, oversized files, invalid
versions, unsafe endpoints and malformed structures fail closed. The schema
is not a credential store.

New routed commands: `ai.profile.configure`, `ai.profile.update`,
`ai.profile.disconnect` (LocalWrite approval required) and
`ai.profile.list` (Read). Their list responses omit endpoints and
credentials; `health=not_checked` explicitly declines network health claims.
Existing `ai.profile.validate` and caller-supplied `ai.providers.list`
remain available for compatibility.

Writes serialize a sorted complete snapshot to a temporary file then replace
the prior snapshot with the OS replacement primitive: `ReplaceFileW` on
Windows and same-filesystem `rename` elsewhere. First creation also uses a
same-directory rename. This removes the earlier Windows gap where a crash
between moving the old file aside and installing the new file could leave no
canonical profile file. Single-writer ownership and directory ACLs remain the
host's responsibility.
Secrets must instead be held in the approved OS credential store. The profile
metadata file includes the endpoint, which can be commercially or personally
sensitive; ensure filesystem access is restricted.

Tests exercise configure denial without approval, explicit router approval
and audit, restart persistence, redacted listing, update/disconnect, duplicate
IDs, unknown/secret fields and schema rejection. The desktop profile CRUD
interface, multi-process locking and live connectivity testing are **not**
implemented here; §40.86 remains PARTIAL.
