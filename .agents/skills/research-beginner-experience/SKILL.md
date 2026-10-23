---
name: research-beginner-experience
description: Create beginner-friendly research onboarding, guided inquiry, contextual teaching, error recovery, and progressive disclosure in a desktop research suite. Trigger on novice journeys and educational UX; avoid changing methodological truth to reduce cognitive load.
---

# Research beginner experience

## When this skill applies

Activate when designing onboarding, first-run projects, research tutorials, novice analysis setup, contextual definitions, example projects, or confusing empty/error states. Design for people who have never conducted research while preserving a path to expert controls. Inputs are target user goals, a set of representative novice tasks, literacy and accessibility considerations, UI constraints, and ideally observed usability feedback. Output a complete first-success journey, instructional microcopy, contextual help, and evidence from task-based testing. Use the methodology integrity skill to validate scientific recommendations.

## Define a first success that is scientifically safe

A first-session task should produce something meaningful within a short interaction: transform a broad interest into an answerable research question; find and save one real paper; extract a source-grounded note; or explore a public demonstration dataset with a defensible descriptive statistic. Do not imply a single paper proves a hypothesis or that a p-value establishes causality. Prepare an offline sample workspace with synthetic or properly licensed content, clear source labels, and a completed expected output. Avoid requiring registration, API keys, a literature-search account, or personal information merely to explore the interface.

Ask users what they want to achieve in everyday language, such as 'Understand what research says' or 'Analyze my own data'. Map intent to workflows with short examples. Explain what an action does, what it needs, whether it changes project data, and what the user gets. Use few initial questions; unknown preferences can be set safely later. Make every suggested template editable and reveal chosen assumptions with a 'Why this?' explanation.

## Layer instruction with the workflow

Use a three-level explanation pattern: a one-sentence actionable description; optional short illustrated explanation with an example; and an advanced technical panel with definitions, assumptions, references, and reproducible commands. Explain terms at the point of use: 'sample', 'variable', 'confounder', 'confidence interval', 'effect size', 'primary source', and 'risk of bias' should each connect to a concrete example. Avoid treating novices as children or interrupting professional users with repeated tutorials. Persist whether help has been dismissed locally and always offer a way to reopen it.

For a literature task, explain differences among a database record, an abstract, a preprint, a peer-reviewed article, and a full-text PDF. Show publication year, DOI or stable link, version, access rights, and verification status. Teach users that a search result can be incomplete or wrong. For data work, ask about units, missing values, categorical vs continuous variables, and the research question before proposing a chart or test. Provide sensible educational defaults as suggestions, not as hidden rules.

Design empty states as actions with context: 'No sources in this project yet. Import a PDF or search a scholarly index' is better than an unexplained blank panel. If a request fails, preserve entered work, explain what happened, link to an actionable remedy, and allow retry. Distinguish invalid user data from inaccessible services or permission failures. Make temporary work recoverable using autosave and explicit project history.

## Guided AI behavior

An assistant must respond to uncertainty with targeted teaching. It should ask for the dependent variable before selecting a regression, surface alternatives, and explain why a chosen method fits the question. For source-based writing, show claims alongside actual supporting snippets and links. Mark generated text as a draft requiring verification. When a user requests an inappropriate claim, explain the methodological mismatch and suggest a corrected interpretation. Offer an 'explain this result' path that covers what the result indicates, what it does not establish, and which assumption checks apply.

Do not silently modify the user's protocol or dataset as part of helping. Offer previews of data transformations and show before/after row counts. Give the learner access to the exact script and metadata so a novice task can mature into reproducible expert work without rebuilding the project. Track educational progress by optional milestones completed, not psychological profiling or opaque engagement scoring.

## Evaluate real usability

Create three representative scenarios: first literature search, first descriptive data visualization, and first claim-to-source citation. Ask participants to narrate what they expect; record completion, time on task, critical errors, help dependence, and whether their interpretation is scientifically correct. Test a user who declines sign-up, has no network, imports an unsupported file, and returns after a restart. Exercise keyboard-only journeys and zoomed text. Do not infer usability from click count alone or use synthetic testimonials.

Acceptance requires users to recognize a meaningful next step, understand the provenance of an example, recover from one injected failure, find expert detail without confusion, and save/export work successfully. The UI must state uncertainty and show how to verify a claim. Record unresolved misconceptions as product defects even if tasks technically complete.

## Sources, safety, and boundaries

Consult [Nielsen Norman Group's progressive disclosure guidance](https://www.nngroup.com/articles/progressive-disclosure/), [The Carpentries instructor training](https://carpentries.github.io/instructor-training/), [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/), [Cognitive Load Theory in educational design](https://doi.org/10.1207/s15326985ep4102_1), and methods references specific to the task. Never present made-up references as teaching examples without conspicuous synthetic labels. Avoid unnecessary collection of age, disability, academic standing, or other personal attributes. This skill controls explanation and affordances; methodological correctness, source verification, and statistics remain their respective specialist domains.
