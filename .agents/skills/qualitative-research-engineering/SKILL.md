---
name: qualitative-research-engineering
description: Engineer auditable qualitative research workflows for transcripts, coding, memos, thematic analysis, and grounded interpretation; activate for interview, focus group, fieldnote, or document analysis features.
---

# Qualitative research engineering

This skill governs qualitative research functionality where preserving context and interpretive provenance matter more than producing a numerical label. Apply it to coding interfaces, interview analysis, field notes, qualitative synthesis, collaborative adjudication, and assisted thematic analysis. Keep researcher interpretation explicit and inspectable.

## Model the source before the code

Treat each source as an immutable imported artifact with a source ID, checksum, language, recording or document metadata, consent restrictions, and version history. The original must remain available to authorized users. Represent extracts through stable offsets, paragraph anchors, timestamps, or transcript turn IDs that survive rendering changes. A quote with no reproducible source span is not valid evidence.

A coding event needs a code ID, label, description, inclusion/exclusion criteria, analyst, timestamp, source span, and optional rationale. Distinguish the code definition from code application. Version codebooks; when a code is renamed, merged, split, or retired, record how prior applications were migrated. Make code hierarchy a user-defined relation, not an assumed ontological truth.

Support overlapping segments and multiple codes applied to the same span. Store independent annotations as events so an analyst can reconstruct revisions, reversals, and disputes. Notes, analytical memos, and reflexive journals require their own types and audit trails. Keep methodological decisions visible in the exported project.

## Workflow patterns

1. Import and transcribe, while explicitly labeling machine transcription versus human-corrected text. Display confidence only when provided by a validated model; do not present it as transcription truth.
2. Let users define research questions, units of analysis, sampling frame, codebook versions, and analytic approach before coding. Avoid enforcing one paradigm across thematic, content, discourse, or grounded-theory work.
3. Build a fast, accessible quote selector with transcript-time synchronization, keyboard coding, contextual previews, and reversible edits. Keep nearby utterances visible so short excerpts are not detached from context.
4. Provide memos and category comparison views, negative-case search, case-by-code matrices, and traces from claims to source spans. Distinguish exploratory charts from inferential statistics.
5. For collaboration, record analyst identity and coding rounds. Facilitate adjudication with side-by-side code applications and preserved disagreements. Do not overwrite one analyst's labels with another's.

## AI-assisted coding boundaries

AI may suggest candidate codes, identify similar passages, propose memo questions, and surface disconfirming examples. Every suggestion must identify the exact excerpt, model/provider/version, prompt template, contextual scope, and acceptance status. Default to review rather than automatic application. Provide visible accept, reject, edit, and undo controls. Never represent generated excerpts, paraphrases, or inferred participant quotations as direct quotes.

Prompt injection may appear inside transcripts and documents. Treat source text as data, delimit it in model calls, and prevent it from changing tool permissions or model instructions. Put restricted participant data only into approved local or contractually authorized providers; disclose provider use and retention implications before any upload. Avoid sentiment labeling as an automatic substitute for qualitative interpretation.

## Methodology-sensitive features

Reflexive thematic analysis does not require inter-rater reliability as a validity gate. For codebook-based content analysis, optional agreement measures may be useful. Offer observed agreement, Cohen's kappa, Krippendorff's alpha, or other statistics only with correct scale, missingness, and unit definitions; label limitations of each statistic. Support analytic saturation discussions without auto-certifying that saturation is achieved.

Exports should include the source manifest, code definitions and history, coding events, memos, analyst roles, and cross-links in open text/JSON/CSV formats. Audit trails should distinguish a generated summary from analyst-authored claims. Preserve cross-language quotation and translation as separately attributed artifacts.

## Failure modes and acceptance

Test overlapping spans, RTL scripts, emoji and grapheme clusters, timestamp drift, duplicate documents, malformed transcripts, thousands of annotations, simultaneous editor conflicts, and codebook migration. Use fixture projects to verify import-export-import invariants: all accepted codes, spans, memos, and attributions survive. Simulate losing network access mid-edit and restoring the project without orphaned references.

Acceptance requires an analyst to trace every reported theme to accepted coded extracts, retrieve the full original context, compare disputed applications, undo any AI suggestion, and export an independently readable project. Research claims always remain subject to methodological review.

## References

Braun and Clarke, thematic analysis resources (https://www.thematicanalysis.net/); COREQ reporting checklist (https://www.equator-network.org/reporting-guidelines/coreq/); W3C Web Annotation Data Model (https://www.w3.org/TR/annotation-model/); FAIR principles (https://www.go-fair.org/fair-principles/). These are methodological and interoperability references, not endorsements of automated qualitative judgments.
