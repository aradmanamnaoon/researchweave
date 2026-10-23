---
name: research-methodology-integrity
description: Review research questions, sampling, study design, measurement validity, causal claims, assumptions, bias, leakage, preregistration, and reporting integrity. Trigger on protocol design or scientific validity concerns, not desktop styling or bibliography formatting.
---

# Research methodology integrity

## Activate for scientific decisions

Use this skill to challenge research plans, analysis claims, data collection designs, secondary analyses, machine-learning evaluations used as scientific evidence, and manuscript methods. Request the question, proposed estimand, target population, design, sampling process, measurement instruments, available data, ethics status, and planned analysis. If any are unknown, classify assumptions visibly instead of inventing them. Output a methodology review with fatal risks, mitigable threats, recommended design or sensitivity checks, and an explicit distinction between what the data identify and what authors hope to claim.

## Start with the estimand

Translate the question into the quantity to be learned: prevalence in a defined population, association conditional on specified covariates, a causal effect under identified assumptions, a predictive performance target, or a qualitative thematic understanding. Define unit of analysis, sampling frame, time horizon, inclusion/exclusion criteria, primary outcome, exposure/intervention, and reference comparison. Specify whether the study is exploratory or confirmatory. Do not call an observed correlation a treatment effect merely because regression covariates were included.

For causal work, articulate assumptions in a DAG or clear text: confounding control, selection mechanisms, measurement error, time order, interference, positivity, consistency, and missingness. Distinguish confounders from colliders and mediators; warn when conditioning can open a biased path or suppress the effect of interest. For randomized designs, inspect randomization unit, allocation concealment, clustering, blinding, attrition, and intent-to-treat analysis. For observational studies, discuss residual confounding and appropriate counterfactual claims.

## Measurement and sampling checks

Confirm construct operationalization, reliability, validity evidence, instrument licensing, cultural adaptation, unit conversion, and whether scale scores can be treated continuously. Flag outcomes defined after observing group differences, predictor leakage into labels, and inconsistent survey waves or harmonization. Document eligible population versus observed sample; identify convenience sampling and coverage bias before suggesting generalization. Report recruitment, exclusions, nonresponse, weighting, attrition, and any repeated measurements requiring within-subject or cluster-aware inference.

For secondary analysis, inspect documentation for design weights, strata, primary sampling units, missing-value codes, item routing, and disclosure controls. Never infer that a numeric sentinel such as -9 represents a legitimate value. For biomedical or neuroscience applications, guard against patient-level data leakage, scanner/site confounding, repeated scans split across training and testing, and post hoc feature selection using the full dataset. Ensure split units correspond to the desired generalization target.

## Analysis and decision integrity

Distinguish pre-specified hypotheses from post hoc discovery, and retain a transparent deviation log. Define the primary outcome and analysis set before looking at results where feasible. Require justification for sample size or precision, not just a generic 'power = 80%' checkbox. Quantify uncertainty with appropriate confidence or credible intervals and report effect sizes. Handle multiple outcomes and researcher degrees of freedom explicitly. Use sensitivity analyses to assess missing data, model specification, influential observations, and plausible unmeasured confounding. Do not treat a non-significant result as evidence of equivalence without an equivalence or precision framework.

In ML experiments, fix data splitting, nested model selection, feature preprocessing, benchmark leakage checks, seeds, hardware, and target metric. Evaluate naive or domain baselines, class imbalance, calibration, confidence intervals, external shift, and subgroup uncertainty when ethically appropriate. Report provenance of pretrained models and training-data overlap risks. For qualitative work, seek transparent sampling, reflexivity, coding decisions, negative cases, audit trail, and appropriately bounded transferability; do not impose p-value logic on thematic interpretation.

## Incident and integrity response

When discovering an error, preserve original inputs, code, reviewer notes, and analysis history. Produce a reproducible discrepancy report identifying claims affected, not a silently patched figure. If a source cannot substantiate a claim, downgrade or remove the claim. Flag evidence of fabricated data, selective reporting, inappropriate duplication, or ethics violations for human review without asserting misconduct from weak signals. Never rewrite dates of preregistration, falsify validation outcomes, or present AI-generated literature findings as independently confirmed.

## Acceptance criteria and references

Check that the question, estimand, design, sample, variables, exclusions, analysis population, uncertainty, missing-data handling, assumptions, sensitivity analyses, and limitations are internally coherent. Demonstrate that cited tables and scripts reproduce the reported sample sizes and quantities. Include at least one plausible alternative explanation and one falsification or robustness check when the method permits. Label open threats explicitly; 'passed' must not mean all biases were eliminated.

Consult [EQUATOR Network](https://www.equator-network.org/) for study-specific reporting guidelines, [CONSORT](https://www.consort-statement.org/) for trials, [STROBE](https://www.strobe-statement.org/) for observational studies, [OSF registries](https://www.cos.io/initiatives/prereg), [Cochrane Handbook](https://training.cochrane.org/handbook), and [American Statistical Association statement on p-values](https://doi.org/10.1080/00031305.2016.1154108). Treat standards as applicable guides, not as automatic evidence of ethical approval. Do not access identifiable participant data or contact human subjects without an authorized and privacy-preserving workflow; respect restricted dataset licenses and embargoes.
