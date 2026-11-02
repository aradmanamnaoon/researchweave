# ResearchWeave local protocol baseline receipt

**Local-only provenance; NOT externally verified preregistration.** The computer clock, local event sequence, event digest and unverified actor do not establish an independent timestamp or identity.

The snapshot digest binds the original persisted protocol version; subsequent amendments are reported without rewriting that version.

## Verified local record

    {
      "local_baseline": {
        "actor_unverified": "desktop-user",
        "current_version": 1,
        "event_hash": "d83f4d22d5d006f1c65e560cdb4758b8e5cab6be4286c24a926729830925dbd8",
        "event_sequence": 2,
        "external_registration_verified": false,
        "frozen": true,
        "frozen_version": 1,
        "local_only": true,
        "post_freeze_amendment_versions": 0,
        "protocol_id": "ff0bc802-a4ef-42f5-aff5-dfdafefc4e72",
        "recorded_at_local_clock": "2026-10-31T16:51:57.660838Z",
        "snapshot_sha256": "ba404012c875744e316d2d96a92b7e54a26760b909ac54c85d30b953f7089f5b"
      },
      "project_id": "5b195086-70b0-44ed-ba2f-c6cf11f20624"
    }
