# GeneAI Research — ML Model Audit Report

**Audit date:** 2026-11-13  
**Project:** GeneAI Research, Phases 1–7  
**Scope:** All machine-learning, deep-learning, docking-score, ADMET, safety, repurposing, biomarker, and “AI” model paths in the repository  
**Companion documents:** `Complete_Audit_Report.md`, `Functional_Test_Report.md`, `Scientific_Validation_Report.md`, `Missing_Features_Report.md`, `Priority_Improvement_Roadmap.md`

> **Audit rule:** model quality is never inferred from a class name, a docstring, or a metric printed by the training script. A model is `PASS` only if a trained artefact exists, its training data and split are documented, and it was evaluated on independent data. No such artefact exists in this repository, so no model-performance claim is marked `PASS`.

---

## 1. Executive summary

### 1.1 Headline result

| Question | Answer |
|---|---|
| Are there any trained model artefacts in the repository? | **No.** No `*.pkl`, `*.joblib`, `*.pt`, `*.pth`, `*.h5`, `*.onnx`, or `*.ckpt` files were found. |
| Is any model independently validated? | **No.** No held-out benchmark, external cohort, calibration study, or prospective validation exists. |
| Is the flagship drug-target model usable? | **No.** It cannot instantiate with the installed RDKit, and its feature contract is inconsistent (2,076 vs 2,080). |
| Are ADMET/safety models real? | **No.** ADMET training data is empty; safety training data is synthetic. |
| Are reported metrics trustworthy? | **No.** Metrics are train-set or demo values; CV standard deviations are hardcoded to `0.0`; selection leakage is present. |
| Is there model provenance/versioning? | **No.** No dataset manifest, version pin, artefact hash, or model card exists. |

### 1.2 Severity distribution

| Severity | Count | IDs |
|---|---:|---|
| CRITICAL | 3 | S-03, F-02, F-01 (dependency-adjacent) |
| HIGH | 6 | S-04, S-06, S-07, S-08, M-01, M-03, M-04, S-11 |
| MEDIUM | 2 | M-02, S-09 |

> F-01 is primarily a dependency-compatibility defect, but it has CRITICAL model impact because it disables the only DTI inference path.

---

## 2. Model and AI-component inventory

| ID | Component | Task | Data source | Artefact | Runtime status | Scientific status |
|---|---|---|---|---|---|---|
| ML-01 | `drug_target_prediction` DTI predictor | Drug–target interaction classification | Built-in 20-sample demo; optional ChEMBL training | None | **FAIL** (RDKit import, then feature mismatch) | **FAIL** |
| ML-02 | Mutation ML | Variant effect/pathogenicity prediction | User-supplied or generated features | None | Runs only if user trains | **FAIL / UNVERIFIED** |
| ML-03 | ADMET prediction | Absorption, distribution, metabolism, excretion, toxicity | `create_sample_training_data()` → `{}` | None | Rule-based/empty | **FAIL** |
| ML-04 | Drug safety / toxicity | Toxicity classification | `create_synthetic_toxicity_data()` (random) | None | Synthetic training only | **FAIL** |
| ML-05 | Drug repurposing | Candidate ranking | Heuristic + partial retrieval; pathway score fixed 0.5 | None | Runs | **PARTIAL** |
| ML-06 | Biomarker discovery | Feature selection/classification | None bundled | None | Runs if user supplies data | **PARTIAL / UNVERIFIED** |
| ML-07 | Deep learning (MLP/GNN) | Molecular/property models | None | None | Import/test failures | **FAIL / UNVERIFIED** |
| ML-08 | Optuna optimization | Hyperparameter search | User data | None | Import failure (`colorlog`) | **FAIL** |
| ML-09 | SHAP explainability | Feature attribution | Model + data | None | Import failure (`slicer`) | **FAIL** |
| ML-10 | MLflow registry/tracking | Experiment/model registry | — | None | Import failure (`yaml`) | **FAIL** |
| ML-11 | Molecular docking “scoring” | Pose ranking | Random rotations + heuristic | None | Runs | **FAIL** (not an ML model, but AI-adjacent scoring) |
| ML-12 | Autonomous agent / biotech assistant | LLM planning/annotation | LLM backend not wired | None | Demo/static only | **UNVERIFIED / FAIL** |
| ML-13 | AI research report generator | Annotation/summarization | Simulated annotation | None | Runs | **FAIL** (fabricated DOI, simulated content) |

**Interpretation:** the repository contains model *code* and model *interfaces*, not model *products*. A user who expects pretrained predictions will either get an error, a demo model, or a heuristic.

---

## 3. Evidence and method

### 3.1 What was inspected

- Model classes, training loops, featurizers, preprocessing, splitting, cross-validation, calibration, and persistence code.
- Test expectations for ML modules.
- Importability and version of ML dependencies.
- Repository-wide search for model artefacts and datasets.
- Runtime execution of the DTI path and a labelled compatibility-shim reproduction.
- Runtime execution of the test suite (107 failures; 9 in `test_ml_enhancements.py`).

### 3.2 What was not possible

- No trained weights to load or evaluate.
- No benchmark dataset bundled.
- No licence to proprietary ADMET/toxicity data.
- No external LLM key.
- No compute budget for retraining from public data during the audit.

Consequently, all quantitative performance statements are `UNVERIFIED` unless they are explicitly identified as *observed training/demo values from the shipped code*.

---

## 4. Findings

### 4.1 S-03 — No trained model artefacts exist (CRITICAL)

**Evidence**

- Repository-wide search for `*.pkl`, `*.joblib`, `*.pt`, `*.pth`, `*.h5`, `*.onnx`, `*.ckpt` returned no model files.
- No bundled training datasets or benchmark splits.
- Prediction classes either require the user to train, fall back to a 20-sample demo, or raise.

**Why it matters**

A model is not a class definition. Without weights, preprocessing state, feature schema, and training provenance, no prediction can be reproduced or audited. Any accuracy/AUC shown in the UI or docs is either a training value or a demo value.

**Status:** `FAIL`  
**Required fix:** publish versioned artefacts + model cards, or remove pretrained-prediction claims and require explicit user training with provenance capture.

---

### 4.2 F-01 — DTI prediction disabled by RDKit incompatibility (CRITICAL model impact)

**Evidence**

- Installed RDKit 2026.9.1 does not expose `rdMolDescriptors.CalcExactMW`.
- `molecular_descriptors.py` treats the missing symbol as “RDKit not installed” and sets `RDKIT_AVAILABLE=False`.
- `DrugTargetPredictor.__init__` raises `ImportError: RDKit is required for molecular feature calculation`.
- UI displays “RDKit is not installed” despite the package being present.

**Why it matters**

The error message misdiagnoses the problem: users may reinstall RDKit repeatedly instead of pinning a compatible version or fixing the descriptor call. The entire DTI feature is unavailable.

**Status:** `FAIL`  
**Required fix:** use a supported descriptor (`ExactMolWt`/`MolWt`) with capability detection; pin and test RDKit; report the actual incompatibility rather than “not installed”.

---

### 4.3 F-02 — Feature contract mismatch (CRITICAL)

**Evidence**

- With a compatibility shim for the missing descriptor, inference supplies 2,080 features while the model expects 2,076.
- Error: `ValueError: X has 2080 features, but SimpleImputer is expecting 2076 features as input.`
- Engine returns `success=False`.

**Why it matters**

The model and featurizer are not a single versioned contract. Even a repaired import would not yield a valid prediction. Any attempt to slice/pad features to fit would silently change the model’s input semantics.

**Status:** `FAIL`  
**Required fix:** define one feature schema (names, order, dtype, handling of missing target features), serialize it with the model, validate it at inference, and fail with a specific schema error.

---

### 4.4 S-04 — Demo training data are trivially confounded (HIGH)

**Evidence**

- 20 samples.
- Positives: drug-like molecules; negatives: short alkanes.
- Default demo model: train accuracy 0.95, train AUC 1.00.
- No held-out test set.

**Why it matters**

A classifier can separate these classes by molecular size, heavy-atom count, or hydrophobicity alone. The metric measures dataset construction, not target–ligand interaction. Presenting it as an interaction model is scientifically misleading.

**Status:** `FAIL`  
**Required fix:** replace with a curated interaction dataset (e.g. a documented ChEMBL/BindingDB extract), time- or scaffold-based splits, matched decoys, and an external test set. Label any demo model explicitly as a smoke test, not a predictor.

---

### 4.5 S-06 — Advertised mutation features are unavailable (HIGH)

**Evidence**

- Preprocessing paths for conservation, AlphaMissense, and UniProt-derived features produce NaN or zero values when the source is unavailable.
- The model interface advertises these features without a visible capability check.
- No imputation provenance or missingness report is surfaced.

**Why it matters**

Silent NaN/zero substitution changes the meaning of every prediction while leaving the UI unchanged. A user cannot tell whether a variant score used one feature or all advertised features.

**Status:** `FAIL`  
**Required fix:** explicit feature-availability reporting; no silent zero-fill; imputation only when trained with that imputation; block prediction when required features are missing.

---

### 4.6 M-01 — Cross-validation standard deviations hardcoded to zero (HIGH)

**Evidence**

- Training code sets CV standard deviations to `0.0` in the reported metrics.

**Why it matters**

A zero standard deviation is a factual claim that every fold produced the same score. It conceals instability and makes hyperparameter choices look more reliable than they are. This is a reporting-integrity defect, not a cosmetic one.

**Status:** `FAIL`  
**Required fix:** compute mean and standard deviation from the actual fold scores; report per-fold values; never synthesize uncertainty.

---

### 4.7 M-02 — Model-selection leakage (MEDIUM)

**Evidence**

- Hyperparameter search and the reported cross-validation score use the same training data.
- The selected configuration is then evaluated on data that participated in selection.

**Why it matters**

Reported CV is optimistically biased. The effect grows with the number of configurations and with small datasets.

**Status:** `FAIL`  
**Required fix:** nested CV or a held-out selection set; report the outer-fold score of the selected pipeline; keep the test set untouched until final evaluation.

---

### 4.8 M-03 — Calibration and validation claims lack evidence (HIGH)

**Evidence**

- Calibration code exists (e.g. isotonic path with `cv=3`), but no reliability diagram, Brier score, or expected calibration error is stored.
- No independent calibration set is documented.
- Claims of “validated” or “calibrated” models are not backed by artefacts.

**Why it matters**

A probability of 0.8 should mean roughly 80% empirical frequency. Without calibration evidence, scores cannot be interpreted as probabilities or used in decision thresholds.

**Status:** `UNVERIFIED` (claims unsupported)  
**Required fix:** calibrate on a dedicated set, report reliability/Brier/ECE, and store the calibration curve with the model.

---

### 4.9 M-04 — No dataset provenance or versioning (HIGH)

**Evidence**

- No dataset manifest, checksum, release version, licence, or preprocessing script version tied to a model.
- Training can silently use whatever data is present at runtime.

**Why it matters**

A model cannot be reproduced, audited, or retired correctly without knowing exactly what it was trained on. This also prevents detecting train/test contamination across releases.

**Status:** `FAIL`  
**Required fix:** immutable dataset snapshots with checksums and licences; a manifest linking data → preprocessing → hyperparameters → artefact hash → evaluation report.

---

### 4.10 S-07 — Drug-safety models use synthetic toxicity data (HIGH)

**Evidence**

- `drug_safety/ml_models.py` calls `create_synthetic_toxicity_data()`.
- Labels are generated rather than derived from assays.
- No model artefact is stored.

**Why it matters**

Synthetic labels can make a model look accurate while teaching it nothing about real toxicity. A safety output based on this cannot be used even for triage.

**Status:** `FAIL`  
**Required fix:** remove synthetic training from any user-facing path; either train on a curated tox dataset with documented endpoints or label the feature as a rules-based screening aid.

---

### 4.11 S-08 — ADMET ML is untrained (HIGH)

**Evidence**

- `admet_prediction.create_sample_training_data()` returns `{}`.
- No models are loaded.
- Rule-based outputs exist but are not equivalent to trained ADMET models.

**Why it matters**

The UI can imply predictive ADMET while the ML path has no data and no model. Rule-based heuristics must be labelled as such.

**Status:** `FAIL`  
**Required fix:** provide trained, validated endpoints with applicability domain, or relabel as “physicochemical rules” and remove predictive language.

---

### 4.12 S-09 — Repurposing is heuristic, not predictive (MEDIUM)

**Evidence**

- Composite evidence scores are heuristic.
- The pathway score is a fixed 0.5 placeholder.
- TTD integration is a placeholder.
- No retrospective or prospective hit-rate evaluation exists.

**Why it matters**

A fixed neutral component changes rankings without biological information, and a heuristic composite is not a probability of success.

**Status:** `PARTIAL`  
**Required fix:** remove or justify the 0.5 constant; document weights; calibrate against known indications; report uncertainty and evidence provenance per candidate.

---

### 4.13 S-11 — No independent external validation (HIGH)

**Evidence**

- No external cohort, benchmark, or prospective evaluation exists for any model.
- No comparison with a published baseline.
- No held-out data separate from model selection.

**Why it matters**

Internal metrics cannot establish generalization. This is the single largest scientific gap across the ML surface.

**Status:** `UNVERIFIED`  
**Required fix:** define an external validation protocol per model; freeze the model; evaluate once; publish the evaluation report with data version and code commit.

---

### 4.14 ML-07 to ML-10 — Deep learning, optimization, explainability, registry are not operational

**Evidence**

- `test_ml_enhancements.py` has 9 failures.
- Optuna 5.0.0 is outside the `<4` pin and fails to import (`colorlog` missing).
- SHAP 0.54.1 fails to import (`slicer` missing).
- MLflow 3.18.0 is outside the `<3` pin and fails to import (`yaml` missing).
- PyTorch is importable (2.15.0), but GNN dependencies are absent; `TORCH_AVAILABLE` produces a `NameError` in one path.

**Why it matters**

The “ML enhancements” layer cannot be used, so there is no working experiment tracking, hyperparameter search, explanation, or graph-neural-network path.

**Status:** `FAIL`  
**Required fix:** lock compatible versions; provide extras; add import smoke tests; separate optional features so their absence does not break core imports.

---

### 4.15 ML-12/13 — LLM/agent and report “AI” paths

**Evidence**

- Autonomous agent planner defaults to `gpt-4` and includes an auto-approve demo path.
- Biotech assistant has no LLM backend wired.
- Report generator contains “simulated” annotation and a fabricated DOI `10.5281/zenodo.xxxxxx`.

**Why it matters**

These are not validated AI components. Fabricated citations and simulated biological assertions are integrity risks, not model-quality issues.

**Status:** `FAIL`  
**Required fix:** remove fabricated content; require a configured provider; log prompts/responses; verify every citation against a real identifier; disable agent autonomy by default.

---

## 5. Cross-cutting methodology assessment

| Requirement | Status | Evidence |
|---|---|---|
| Documented task definition | **PARTIAL** | Some classes/docstrings define tasks; endpoints/metrics are not consistently specified. |
| Curated training data | **FAIL** | Demo/synthetic/empty. |
| Data licences | **FAIL** | No licence manifest found. |
| Train/validation/test separation | **PARTIAL** | Some pipelines split; DTI demo does not. |
| Nested CV / selection isolation | **FAIL** | Selection leakage in mutation ML. |
| Class imbalance handling | **UNVERIFIED** | Not demonstrated for the audited paths. |
| Feature schema versioning | **FAIL** | 2,076 vs 2,080 mismatch. |
| Missing-data policy | **FAIL** | Silent NaN/zero substitution. |
| Leakage controls (scaffold/time) | **FAIL** | No scaffold/time split evidence. |
| Metric appropriateness | **PARTIAL** | Accuracy/AUC only in places; no PR-AUC for imbalance, no calibration. |
| Uncertainty reporting | **FAIL** | Zeroed CV stds; no CIs. |
| Calibration | **UNVERIFIED** | Code path exists; no evidence. |
| Applicability domain | **ABSENT** | No OOD/AD checks. |
| External validation | **ABSENT** | None. |
| Model cards | **ABSENT** | None. |
| Artefact versioning | **ABSENT** | No artefacts. |
| Reproducibility seeds | **UNVERIFIED** | Not demonstrated. |
| Monitoring/drift | **ABSENT** | No production monitoring. |
| Explainability | **FAIL** | SHAP unimportable; no stored attributions. |
| Fairness/bias review | **NOT APPLICABLE / ABSENT** | No human-subject data identified, but model bias still unaudited. |

---

## 6. Metrics: observed versus validated

| Metric | Value observed | Context | Validated? |
|---|---|---|---|
| DTI demo train accuracy | 0.95 | 20-sample confounded demo | **No** |
| DTI demo train AUC | 1.00 | Same | **No** |
| Mutation ML CV mean | Computed at runtime | No artefact/test set | **No** |
| Mutation ML CV std | `0.0` | Hardcoded | **No — invalid** |
| ADMET metrics | None | Empty training factory | **No** |
| Safety metrics | None | Synthetic labels | **No** |
| Biomarker metrics | None | No dataset | **No** |
| Docking score | Heuristic | Random rotations | **No** |
| Repurposing score | Heuristic + 0.5 placeholder | No validation | **No** |

**No value in this table should be quoted as model performance.** The only defensible statement is that the demo model separates its own two contrived classes.

---

## 7. Model risk classification

| Component | Risk if used for decisions | Reason |
|---|---|---|
| DTI predictor | **Critical** | Cannot run; if forced, confounded demo/feature mismatch. |
| ADMET | **Critical** | No model; rule outputs may be mistaken for predictions. |
| Safety/toxicity | **Critical** | Synthetic labels; could misclassify hazardous compounds. |
| Docking/scoring | **Critical** | Random poses + energy-like units. |
| Mutation ML | **High** | Missing features, leakage, zeroed uncertainty. |
| Repurposing | **High** | Placeholder/untested composite. |
| Biomarker | **High** | No data/validation; overfitting risk. |
| Genome conservation | **High** | Random values presented as biology. |
| Report/LLM | **High** | Fabricated DOI/simulated annotation. |

**Overall model risk: CRITICAL — do not use any model output for research conclusions, compound prioritization, safety assessment, or clinical interpretation.**

---

## 8. Required remediation and validation gates

### 8.1 P0 — Stop misleading outputs (days)

1. Disable or relabel DTI, ADMET, safety, docking, and conservation outputs as “unvalidated/demo”.
2. Remove synthetic/simulated content from user-facing reports.
3. Fix the RDKit descriptor call and report the real incompatibility.
4. Fix or explicitly reject the 2,080 vs 2,076 feature schema.
5. Add a startup capability report (models loaded, data versions, optional deps).

**Gate:** no user-facing prediction without a model artefact + model card; no fabricated citation; no random biological track labelled as data.

### 8.2 P1 — Establish reproducibility (2–6 weeks)

1. Create immutable dataset snapshots with checksums and licences.
2. Define a versioned feature schema per model.
3. Replace hardcoded CV stds with computed values.
4. Implement nested CV or a held-out selection set.
5. Store preprocessing, hyperparameters, seeds, and artefact hash.
6. Add model cards with intended use, limitations, and metrics.

**Gate:** retraining from the manifest reproduces the artefact hash and metrics within a documented tolerance.

### 8.3 P2 — Independent validation (6–12 weeks)

1. DTI: curated interaction dataset, scaffold/time split, external test, calibration, applicability domain.
2. Mutation ML: real conservation/AlphaMissense/UniProt features, no silent zero-fill, external variant set.
3. ADMET/safety: curated assay endpoints with documented tox labels; external test; calibration.
4. Docking: install Vina/Smina/GNINA; redocking RMSD; enrichment; affinity correlation.
5. Biomarker: pre-registered pipeline on an independent cohort; multiple-testing control.
6. Repurposing: retrospective hit-rate; remove the 0.5 placeholder or justify it.

**Gate:** each model has an evaluation report with external data, confidence intervals, calibration, and a limitations section.

### 8.4 P3 — Operational maturity (12+ weeks)

1. Model registry with stage transitions and rollback.
2. Input drift and performance monitoring.
3. Periodic revalidation and retirement policy.
4. Audit trail linking every prediction to model/data/code versions.
5. Access control and signed model artefacts.

---

## 9. Minimum model-card template

Every model endpoint must publish:

| Field | Requirement |
|---|---|
| Model ID/version | Immutable identifier and artefact hash |
| Task | Classification/regression/ranking; label definition |
| Intended use | Explicit in-scope and out-of-scope uses |
| Training data | Source, licence, version, checksum, size, label distribution |
| Split strategy | Random/scaffold/time; leakage controls |
| Features | Names, order, dtype, missing-data policy, version |
| Preprocessing | Fitted transformers, serialized with the model |
| Hyperparameters | Search space, selection metric, selected values |
| Metrics | Mean ± std, per-fold, confidence intervals |
| Calibration | Method, calibration set, reliability/Brier/ECE |
| External validation | Dataset, metrics, date, evaluator |
| Applicability domain | Method and thresholds |
| Limitations | Known failure modes, bias, OOD behaviour |
| Ethical/regulatory | Clinical use status, disclaimers |
| Reproduction | Command, environment lock, seed, data snapshot |
| Owner/review | Responsible person and review date |

None of the audited models currently satisfies this template.

---

## 10. ML audit conclusion

The repository has a broad ML *surface* but no validated ML *product*. The absence of artefacts is the root fact from which most other findings follow: without weights, feature schemas, data manifests, and evaluation reports, the platform cannot substantiate any predictive claim. The DTI path is additionally blocked by two independent defects, ADMET/safety are placeholder/synthetic, mutation ML has integrity defects in its reporting, and the enhancement stack (Optuna/SHAP/MLflow/GNN) does not import.

**Recommendation:** freeze all model-facing claims; repair the feature contract and dependency issues; build reproducibility infrastructure; then validate one model at a time on external data. Do not add new model families until at least one existing model passes an independent validation gate.

---

*End of ML Model Audit Report.*
