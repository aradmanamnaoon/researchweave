# §40.57 — persisted qualitative provenance

The project-scoped read capability `qualitative.mixed_provenance` reconstructs
the canonical `coding_hash` from persisted qualitative codes and annotations,
using the same ordered serialization as `qualitative.inspect`. It returns
active `codebook_ids` and verified annotation metadata (source ID, code ID,
body SHA-256, Unicode-character span and quotation SHA-256).

For every persisted annotation it reloads the source from `document_text`,
checks the body's actual SHA-256 against both the stored document hash and
annotation hash, confirms active code membership and verifies that the
exact Unicode-character span matches the recorded quote. The operation
rejects caller-supplied coding hashes and quotes and returns no raw quotation.
It is read-only and cannot bypass router approval for the separate
`mixed.joint_display_sensitive` capability.

Schema v5 resolves the former case-mapping gap explicitly rather than by
inference. `qualitative_transcripts` maps each persisted transcript source to
a bounded quantitative `case_id`, records confidentiality and the verified
body SHA-256, and participates in the canonical content hash. The provenance
read emits `case_mapping_available=true` only when every coded source has an
explicit valid mapping; its `qualitative_cases` includes mapped uncoded cases
as well as coded ones and never contains raw quotes.

The desktop host consumes this read directly for
`mixed.persisted_joint_display`; callers cannot inject a replacement coding
hash or case map. This closes the previously documented persistence-to-analysis
composition gap while keeping the analysis crate independent of evidence
storage.

Evidence tests exercise provenance consistency after a reopen, exact quote
digest, absence of quote disclosure, transcript mapping replay/stale-hash
failure and refusal of untrusted state. Desktop integration additionally
verifies the persisted snapshot against an immutable dataset revision.
