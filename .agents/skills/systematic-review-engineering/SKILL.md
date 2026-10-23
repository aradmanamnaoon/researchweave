---
name: systematic-review-engineering
description: Engineer auditable systematic and scoping review workflows with registered protocols, reproducible searches, deterministic deduplication, dual screening, extraction, risk-of-bias assessment, and PRISMA flow accounting. Trigger on evidence synthesis platforms and review automation.
---

# Systematic review engineering

## Activation and research scope

Use when implementing or validating a systematic review, scoping review, living review, or structured evidence map. Ask for review question framework (PICO, PECO, SPIDER, or suitable equivalent), protocol, eligibility criteria, databases, reviewers, search dates, screening requirements, and synthesis plan. Output a review data schema, versioned search/decision workflow, evidence logs, count reconciliation, and export compatible with reporting requirements. Do not treat an LLM's relevance judgment as a reviewer consensus or permit the interface to invent excluded studies.

## Protocol as a controlled input

Record review type and question, population/phenomenon, intervention/exposure, comparison, outcomes, study designs, date/language and publication restrictions, target databases, planned screening levels, extraction fields, risk-of-bias instruments, and synthesis methods. Track registration identifiers such as PROSPERO or OSF when relevant and preserve timestamped protocol versions. Later changes need author, date, rationale, and an explicit note about when evidence was seen. Never overwrite an earlier protocol to make post hoc decisions appear preplanned.

Design an immutable audit trail around a study-centric identifier. Distinguish a retrieved search record, a unique report, a study, and a study outcome; one randomized trial may generate multiple papers, reports, or follow-ups. The primary deduplication key can include verified DOI, PMID and repository identifier; normalized title/year/author similarity yields a review queue rather than automatic irreversible merges. Preserve original imported records and log every decision to merge or separate linked reports.

## Search and screening engine

Translate the protocol to each database's supported syntax with tested parenthesis/field translations. Save exact search strings, provider, interface, date, filters, record counts and retrieval files. Capture supplemental citation chaining, handsearching, registry results, and expert-supplied records as distinct sources. Track reruns for living reviews to avoid double-counting previously retrieved records.

Implement title/abstract and full-text screening as separate stages with explicit inclusion, exclusion, unsure, and not-yet-assessed states. For dual screening, preserve blinded independent votes until both reviewers finish, then expose disagreement resolution. Do not automatically reconcile votes in favor of inclusion or exclusion without configured protocol rules and recorded arbitration. At full text, require a standardized reason for exclusion with mutually exclusive primary reason and optional detailed notes; preserve file access attempts and retrieval failures separately from genuine exclusion.

Treat AI prioritization as optional queue ordering. Record model version, features, training examples, thresholds, false-negative evaluation and human sign-off. If a model suggests exclusion, retain human review for any exclusion unless the registered protocol, governing standards, and reviewer approvals explicitly authorize the automation. Measure recall on representative manually labeled studies and report confidence intervals; raw accuracy is insufficient for low-prevalence inclusion tasks.

## Extraction and appraisal

Configure forms with field type, unit, permissible values, source locator, reviewer, revision and validation. Extract intervention doses, sample denominators, outcomes, effect sizes, standard errors, follow-up times, and subgroups with explicit units and definitions. Store original reported figures adjacent to derived standardized values; never silently convert odds ratio, risk ratio, standardized mean difference, or hazard ratio into one interchangeable effect. Differentiate missing, not reported, not applicable, and extraction error. Support double extraction or sampled verification and adjudication.

Risk of bias is design-specific: use instruments such as RoB 2 for randomized trials and ROBINS-I for nonrandomized interventions when appropriate; don't assign a universal numerical quality score without methodological justification. Associate judgments with signaling questions, evidence quotes, and an assessor. Prepare GRADE or other certainty assessment separately from individual study risk of bias.

## Synthesis and PRISMA audit

Make PRISMA counts computed from event/state transitions: records identified by source, removed before screening (duplicates/automation/other), screened, excluded, sought for retrieval, not retrieved, assessed for eligibility, reports excluded by reason, and studies included. Reconcile counts and enforce nonnegative arithmetic; report both studies and reports in final inclusion. Permit narrative synthesis when pooling assumptions fail. For meta-analysis, require compatible outcome definitions, effect measures, uncertainty, dependence handling, heterogeneity methods, missing-study sensitivity, and appropriate plots. Separate exploratory subgroup analysis from preplanned comparisons.

## Adversarial tests and acceptance

Test a DOI duplicate with conflicting metadata, multiple reports from one trial, a report with no full text, blinded reviewers with opposite votes, an updated search, missing extraction units, one study with multiple correlated effects, and a withdrawn paper. Verify every PRISMA count can be recomputed from stored decisions and that exports retain reviewer provenance. Simulate interrupted imports and reviewer synchronization conflicts; no decisions may silently disappear. An acceptably engineered system produces a complete audit file, reproduces identification-to-inclusion flow from fixtures, surfaces unresolved conflicts, and accurately labels unverified AI recommendations.

## References, privacy, and limits

Refer to [PRISMA 2020](https://www.prisma-statement.org/prisma-2020), [PRISMA-S](https://doi.org/10.1186/s13643-020-01542-z), [Cochrane Handbook](https://training.cochrane.org/handbook), [JBI guidance](https://jbi.global/critical-appraisal-tools), [RoB 2](https://www.riskofbias.info/welcome/rob-2-0-tool), and [GRADE](https://www.gradeworkinggroup.org/). Verify version-specific recommendations at use time. Never bypass publisher access controls to fetch full texts, expose reviewer identities when blinding is required, or submit a registration on a user's behalf without explicit approval. This skill governs evidence synthesis workflow; bibliographic identity, retrieval adapters, and numerical estimators should be validated by their specialist skills.
