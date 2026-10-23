# ResearchWeave V2 evidence — live provider acceptance

Observed: 2026-10-23. Branch: `rebuild/v2-evidence`. Transport: permissioned `StdlibHTTPS` with
fixed HTTPS host allowlist, redirects disabled, bounded responses and no project telemetry.

The acceptance probe used the public DOI `10.1056/NEJMoa2034577` and transmitted no private research
data. The normalized expected work was *Safety and Efficacy of the BNT162b2 mRNA Covid-19 Vaccine*,
published in 2020. Provider metadata remained explicitly unverified scientific evidence.

| Provider | Result | Provider ID | Response SHA-256 |
|---|---|---|---|
| Crossref | exact DOI reported; title/year matched | `10.1056/nejmoa2034577` | `9bf9917b2b72924eaeaf1224e749e22b32a9004d87ddc3968e16bbbfd076ae22` |
| OpenAlex | exact DOI reported; title/year matched | `https://openalex.org/W3111255098` | `ec2b3149204a434c1ee4afedad71228717fa61a7917b17be6a9b4695e44fa9fb` |
| PubMed | exact DOI reported; title/year matched | PMID `33301246` | ESearch `655b9ffccc3d63ba3c88c9bcbe6cb439ad7f9972998156ac60dba14e84d6e242`; ESummary `5a0f054458d02c4b089636120889cfc01b7ba69194725bfef7a7d41ddc9ed1b2` |
| Europe PMC | exact DOI reported; title/year matched | `33301246` | `c3edc60cce13bb0480ddc4520592cf7be7fa522298ed0209073c16313800a0bc` |

The same run exercised an opted-in Crossref `reference.watch_check`. It returned
`catalog_presence=reported`, recorded Crossref response hash
`9bf9917b2b72924eaeaf1224e749e22b32a9004d87ddc3968e16bbbfd076ae22`, reported
`metadata_updated=false`, required human confirmation, persisted one observation-history row and
left the user-confirmed reference title and year unchanged.

Deterministic injected-transport tests remain the acceptance evidence for malformed JSON, HTTP
errors, `Retry-After`, offline denial, optional credentials, pagination, partial batch failures and
per-request throttling. This live note proves current public endpoint compatibility on the observed
date; it does not assert future provider availability, quota policy or scientific truth.
