# Integration support matrix

Support labels are intentionally narrow: **native verified**, **file import/export verified**, **limited/conditional**, **experimental**, and **not supported**.

| Integration | Level | Current behavior |
|---|---|---|
| Local ResearchWeave project storage | native verified | Local project state, backups, recovery and audit metadata are exercised by tests. |
| CSV / TSV | file import/export verified | Scientific import/export paths are covered, including Unicode and formula-safe export. |
| XLSX / ODS / Parquet | file import/export verified | Optional format dependencies are in the canonical `formats` extra and covered by analysis tests. |
| SPSS `.sav` / Stata `.dta` | file import/export verified | Import metadata/labels are covered through `pyreadstat`; no proprietary SPSS runtime is bundled. |
| PDF | limited/conditional | Text extraction uses `pypdf`; scanned-image OCR requires an external OCR path and is not fabricated. |
| DOCX / PDF manuscript export | limited/conditional | Implemented with `python-docx` / ReportLab; complex source formatting may not round-trip exactly. |
| Zotero | file import/export verified | Exported-library and local bridge workflows exist; direct cloud-account synchronization is not claimed. |
| OpenAlex / Crossref / PubMed / Europe PMC | limited/conditional | Evidence facade has explicit network operations with injected transport and allow/consent requirements. Offline default remains active. |
| Local model runtime / Ollama adapter | limited/conditional | Backend adapter exists; local runtime must be installed/configured by the user. Core research workflow does not depend on it. |
| Remote AI providers | limited/conditional | Provider adapters exist behind egress policy and explicit approval. No consumer-subscription credential reuse is supported. |
| Durable local AI agents | native verified | Retrieval-backed planning/execution is covered by AI tests and integrated command-bus tests. |
| Encrypted local archive | native verified | Evidence/AI cryptographic paths use `cryptography`; wrong-key/tamper behavior is tested in worker suites. |
| R runtime | limited/conditional | Optional subprocess path is present. Local Windows verification observed the graceful missing-R path only. |
| Linux portable build | experimental | Build script and CI runner definition exist; not observed in this Windows session. |
| macOS portable build | experimental | Build script and CI runner definition exist; not observed in this Windows session. |

## Desktop AI caveat

The desktop Provider/Agent/Privacy screens expose optional provider configuration and proposal controls. Advanced AI facade operations such as provider completion, retrieval answers and durable agent execution are available through the shared backend command bus, but not all are wired to direct desktop controls yet. This is a release-completeness gap, not a backend availability claim.
