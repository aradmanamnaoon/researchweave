---
name: scientific-research-workflows
description: Design end-to-end research project workflows from question and protocol through sources, data, analysis, interpretation, manuscript, and reproducible export. Trigger on workflow orchestration and project state; defer specialist statistical, citation, and review algorithms to dedicated skills.
---

# Scientific research workflows

## Scope and expected artifact

Use when building a connected research workspace, deciding project lifecycle stages, automating handoffs, or repairing inconsistencies between a protocol, dataset, analysis, and manuscript. Support qualitative, quantitative, mixed-method, and literature-only work without pretending every discipline has an identical process. Inputs include a research question, domain, methodological assumptions, collaborators, source constraints, human-subjects classification, output targets, and existing repository objects. Deliver a navigable state machine, provenance-aware domain model, and tested user journey. An AI assistant may propose actions at every stage, but user review is required for consequential scientific claims, publication, external data transmission, or destructive data operations.

## Model the research project as linked evidence

Define stable project, question, hypothesis, protocol, source, dataset, variable, analysis, result, claim, citation, and export entities. Give each entity a version and provenance link. Relationships must survive renaming, moving documents, changing citation styles, and re-running an analysis. Track the distinction among user-entered facts, imported metadata, computed results, external search responses, and AI-generated suggestions. Do not overload one generic 'note' type for all these concepts.

Represent the workflow as revisitable stages rather than a rigid irreversible wizard. A practical sequence is question and scope; prior-art discovery; methods and protocol; collection or evidence extraction; quality assessment; cleaning; analysis or synthesis; claim review; writing; submission/export; and post-publication maintenance. Each stage requires explicit entry criteria, deliverables, and links to upstream evidence. Users must be able to revise their question later while seeing which analyses, outputs, and claims are invalidated.

Record process decisions including inclusion criteria, changes to the protocol, exclusion reasons, sample definitions, variable transformations, missing-data strategy, planned contrasts, analytical software versions, and collaborator approvals. Distinguish a plan written before results from a retrospective change. An optional preregistration pointer should be read-only once filed; subsequent deviations remain visible instead of rewriting history.

## Implement workflow actions

1. Start a project with a minimum viable question, type of evidence, expected final output, and privacy preference; explain unknowns instead of forcing arbitrary defaults. Provide selectable templates for an exploratory review, empirical analysis, qualitative coding, and systematic review, each with editable stage requirements.
2. Create a task graph of dependencies and statuses: draft, ready, running, requires review, completed, superseded, and failed. Show blockers as actual missing dependencies, not invented percentages of overall research completion.
3. Connect source acquisition to deduplication, rights and extraction metadata. Store the original object, normalized interpretation, parser version, and reviewer corrections separately. Preserve quoted excerpts with exact page or section anchors when available.
4. Record data dictionary, unit definitions, sampling frame, consent/usage restrictions, analysis scripts, environment lock, random seeds, outputs, uncertainty, and diagnostics. Results must link to the exact dataset snapshot and code revision that generated them.
5. Build an evidence-to-claim inspector. When text says a relationship is statistically significant, show supporting output, model definition, comparison, sample count, assumptions, and caveats. Unsupported or contradicted statements receive a review flag.
6. Export a portable package: human-readable project summary, source identifiers, analysis configuration, manifest with hashes, and chosen open formats. Mark nonredistributable source material as references rather than bundling it without permission.

## AI-assisted interaction contract

The assistant needs explicit tool permissions and scoped input objects. Separate read, suggest, draft, modify, run, and publish capabilities. Present proposed transformations with previews and meaningful diffs. Record tool arguments, outputs, source snapshots, verification state, failures, user decisions, and timestamps. Every generated claim should carry a confidence or verification status grounded in actual evidence, never a fabricated numeric certainty. If a literature search API is unavailable, surface the limitation and offer a reproducible manual import route.

Research novices need plain descriptions of methodological alternatives and uncertainty. Experienced researchers need direct access to parameters, scripts, provenance and revisions. Offer two presentation depths over the same underlying research model so convenience cannot silently weaken rigor. A single step may be run independently when its prerequisites exist; support branching scenarios rather than silently overwriting results.

## Failure modes and validation

Detect stale downstream outputs after upstream edits. Avoid mutable input files whose latest contents cannot be tied to a past result. A failed retrieval must never produce a success citation; a draft title must never become a verified source. Catch mismatched units, dataset IDs, different sample filters, missing extraction metadata, and contradictory protocol versions. Require human confirmation for ethics-sensitive procedures or unsupported causal interpretations.

Test a synthetic full path from question to export, then change the source and verify affected summaries and citations are marked stale. Simulate an offline literature API, a canceled analysis, duplicate imports, two collaborators editing a note, and an export with restricted attachment rights. Verify that users can inspect why each claim exists, undo local edits where possible, reopen exports, and reproduce a computed artifact from recorded inputs. Record which stages were actually tested, and never claim a completed scientific study from a functioning software pipeline.

## References and boundaries

Use [FAIR Guiding Principles](https://www.go-fair.org/fair-principles/), [W3C PROV-O](https://www.w3.org/TR/prov-o/), [Center for Open Science](https://www.cos.io/), [RO-Crate](https://www.researchobject.org/ro-crate/), and discipline-specific standards such as PRISMA where applicable. Provenance and reporting standards guide software structure; they do not certify scientific validity. Keep identifiable participant data local or in explicitly approved storage, exclude secrets and private raw files from routine exports, and do not initiate recruitment, ethics approval, publication, or external submission without explicit authorization.
