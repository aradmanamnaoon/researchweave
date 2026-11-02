# Hosted Linux native GUI — Protocol physical receipt path readback

Evidence: exact-source `b7b007d` native release candidate run `41292572192`,
artifact `rust-linux-full-native-gui-evidence`, executable Xvfb/AT-SPI job.

The real native Protocol freeze path passed the following before the failure:

```text
AT_SPI_NATIVE_PROTOCOL_INSPECTOR_READ=frozen:false
AT_SPI_NATIVE_PROTOCOL_INSPECTOR_READ=frozen:true
LOCAL_PROTOCOL_FREEZE_ACCESSIBLE_SUMMARY_OK
AT_SPI_NATIVE_PROTOCOL_INSPECTOR_JSON_DIGEST_OK
```

The next physical receipt Save step typed the exact absolute destination
string into the Slint field. AT-SPI `queryText()` returned **empty text** on
three repeated reads, rather than throwing `NotImplementedError`. The
prior helper tolerated the latter but refused the former and exited before
the physical artifact oracle. This is an observed accessibility readback gap,
**not proof that native Save actually used the typed path**.

Fix: introduce an explicit `allow_zero_readback` flag (off by default), used
only for that physical receipt filename field. Nonempty *wrong* readback
remains a hard failure. This defers its typing proof to the next, existing
strict real native Save verification, which requires the exact requested
path to appear as an actual file, with the persisted protocol SHA-256, the
literal local-only/not-externally-verified provenance, and a physical digest
shown by the UI. No invented file, synthetic SQLite write, unconditional
success marker or skipped negative assertion is permitted.

**Status:** Python syntax verified. The updated full native Xvfb/AT-SPI
journey still needs a successful exact-source hosted/local rerun before a
release may cite this as accepted. The zero-length AT-SPI Text readback
is an accessibility limitation and should be tracked separately.
