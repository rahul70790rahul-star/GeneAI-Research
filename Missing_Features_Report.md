# GeneAI Research — Missing Features Report

**Audit date:** 2026-11-13  
**Project:** GeneAI Research, Phases 1–7  
**Scope:** Features that are absent, advertised but non-functional, present only as placeholders, or required to make an existing claim credible  
**Companion documents:** `Complete_Audit_Report.md`, `Functional_Test_Report.md`, `Scientific_Validation_Report.md`, `ML_Model_Audit_Report.md`, `Priority_Improvement_Roadmap.md`

> **Scope rule:** this report does **not** propose Phase 8 features. Every gap below is either (a) part of the Phase 1–7 scope, (b) required to make an existing Phase 1–7 claim true, or (c) a production/security control needed before Phase 7 can be called complete.

---

## 1. Summary

The platform’s core parsing and retrieval features exist. The largest missing areas are:

1. **Trained, validated models** — the repository contains no model artefacts.
2. **A working drug-target prediction path** — blocked by dependency and feature-contract defects.
3. **A real docking/scoring engine** — currently random rotations plus heuristic scores.
4. **ADMET and toxicity models with real data** — currently empty or synthetic.
5. **Real disease/genomics evidence** — GWAS/HPO association stubs, random conservation track.
6. **Laboratory, data-management, and QA capabilities** — explicitly listed as unimplemented in the project’s own Phase 6 status.
7. **Production security and operations** — no app authentication, hardcoded API key, open bind, no verified health/monitoring/backup.
8. **Product honesty and navigation** — fabricated dashboard, placeholder pages, two dead routes, 21 unreachable modules.

### 1.1 Gap counts by category

| Category | Gaps | Highest severity |
|---|---:|---|
| Scientific modelling | 9 | CRITICAL |
| Data and knowledge | 6 | CRITICAL |
| Laboratory / Phase 6 | 4 | HIGH |
| Security and access | 5 | CRITICAL |
| Operations and reliability | 5 | HIGH |
| Product / UX honesty | 5 | HIGH |
| Engineering and test | 4 | HIGH |
| **Total** | **38** | — |

---

## 2. Gap register

### 2.1 Scientific modelling

#### MF-01 — No trained model artefacts or model cards

| Field | Value |
|---|---|
| Phase | 4–7 |
| Severity | **CRITICAL** |
| Status | Missing |
| Evidence | No `*.pkl`, `*.joblib`, `*.pt`, `*.pth`, `*.h5`, `*.onnx`, or `*.ckpt` anywhere; no model card/manifest; no bundled benchmark. |
| Impact | No predictive claim can be reproduced, audited, or deployed. |
| Required | Versioned artefacts, feature schemas, preprocessing state, model cards, evaluation reports. |
| Depends on | MF-18/MF-19/MF-27 |

#### MF-02 — Drug-target prediction does not work end-to-end

| Field | Value |
|---|---|
| Phase | 4 |
| Severity | **CRITICAL** |
| Status | Broken |
| Evidence | RDKit 2026.9.1 lacks `CalcExactMW` → predictor raises `ImportError`; with a shim, 2,080 inference features vs 2,076 expected. |
| Impact | Flagship Phase 4 feature is unusable. |
| Required | Fix descriptor call; unify feature schema; add contract tests; validate on an interaction dataset. |
| Depends on | MF-01 |

#### MF-03 — No validated docking engine

| Field | Value |
|---|---|
| Phase | 4 |
| Severity | **CRITICAL** |
| Status | Missing / mislabelled |
| Evidence | No `vina`, `smina`, `gnina`, `qvina2`, or `qvina-w` on `PATH`; `_dock_internal` uses random rigid-body rotations. |
| Impact | Poses and scores are not docking results. |
| Required | Integrate a validated engine; receptor/ligand preparation; redocking RMSD; enrichment validation; or relabel as a non-docking heuristic and remove kcal/mol claims. |
| Depends on | MF-04 |

#### MF-04 — No physically meaningful scoring / MM-GBSA

| Field | Value |
|---|---|
| Phase | 4 |
| Severity | **HIGH** |
| Status | Missing / placeholder |
| Evidence | “Vina/RF-Score/NNScore” are simplified approximations; MM/GBSA GB term returns `0.0`. |
| Impact | Energy-like numbers have no demonstrated relationship to binding. |
| Required | Use validated scoring functions or clearly label heuristics; implement/validate MM-GBSA or remove it. |

#### MF-05 — ADMET models and training data are absent

| Field | Value |
|---|---|
| Phase | 4 |
| Severity | **HIGH** |
| Status | Missing |
| Evidence | `create_sample_training_data()` returns `{}`; no models loaded; rule-based outputs only. |
| Impact | No predictive ADMET capability. |
| Required | Curated endpoint datasets, trained models, applicability domain, external validation, or explicit “rules only” labelling. |

#### MF-06 — Toxicity/safety models use synthetic data

| Field | Value |
|---|---|
| Phase | 4 |
| Severity | **HIGH** |
| Status | Placeholder |
| Evidence | `create_synthetic_toxicity_data()`; no artefact; “pretrained” path is a placeholder. |
| Impact | Safety predictions are not evidence-based. |
| Required | Curated tox endpoints, documented labels, external validation, or remove predictive claims. |

#### MF-07 — Mutation ML lacks its advertised feature sources

| Field | Value |
|---|---|
| Phase | 4 |
| Severity | **HIGH** |
| Status | Partial |
| Evidence | Conservation, AlphaMissense, and UniProt features resolve to NaN/zero; no availability report. |
| Impact | Predictions silently use different information than advertised. |
| Required | Wire real feature sources; block prediction when required features are missing; report missingness. |

#### MF-08 — Real disease/gene association is absent

| Field | Value |
|---|---|
| Phase | 6 |
| Severity | **HIGH** |
| Status | Stub |
| Evidence | `genomic_intelligence/disease_associator.py` methods return `[]` for disease/GWAS/HPO association. |
| Impact | Genomic intelligence cannot associate genes/variants with disease. |
| Required | ClinVar/Open Targets/GWAS/HPO integration with evidence provenance and FDR control. |

#### MF-09 — GWAS Catalog client is absent

| Field | Value |
|---|---|
| Phase | 6 |
| Severity | **HIGH** |
| Status | Missing |
| Evidence | Legacy REST API returns HTTP 410; no GWAS client module in `geneai/`. |
| Impact | No variant–trait association evidence. |
| Required | Client for the current GWAS Catalog API, with pagination, release version, and licence metadata. |

#### MF-10 — Real conservation tracks are absent

| Field | Value |
|---|---|
| Phase | 6 |
| Severity | **HIGH** |
| Status | Fabricated placeholder |
| Evidence | Genome browser uses `np.random.beta(2, 5, 100)` and labels it “PhastCons”. |
| Impact | Fabricated biological evidence. |
| Required | Remove random data; ingest real PhastCons/phyloP or label the panel “synthetic demo”. |

#### MF-11 — Biomarker discovery has no data or validation

| Field | Value |
|---|---|
| Phase | 5 |
| Severity | **HIGH** |
| Status | Partial |
| Evidence | Recognizable sklearn methodology; no bundled dataset, no result, no external cohort. |
| Impact | No biomarker claim can be supported. |
| Required | Curated dataset, pre-registered pipeline, multiple-testing control, external validation. |

#### MF-12 — Repurposing lacks validated scoring

| Field | Value |
|---|---|
| Phase | 4–5 |
| Severity | **MEDIUM** |
| Status | Partial |
| Evidence | Heuristic composite; pathway score fixed at 0.5; TTD placeholder; no retrospective hit-rate. |
| Impact | Rankings are not evidence of repurposing probability. |
| Required | Remove/justify placeholder; calibrate; retrospective validation; per-candidate evidence provenance. |

#### MF-13 — Integrated precision pipeline is incomplete

| Field | Value |
|---|---|
| Phase | 4–5 |
| Severity | **MEDIUM** |
| Status | Placeholder |
| Evidence | Literature stage returns zero/placeholder; ML toxicity stage absent; composite not validated. |
| Impact | End-to-end conclusion is not supported by all stages. |
| Required | Complete stages or remove the pipeline from the UI; validate the composite. |

#### MF-14 — Molecule generator does not attach substituents

| Field | Value |
|---|---|
| Phase | 4 |
| Severity | **MEDIUM** |
| Status | Broken |
| Evidence | `_attach_substituents` ends in `pass`; scaffold hopping does not modify the scaffold. |
| Impact | “Generated” analogues may be identical to the input or chemically unmodified. |
| Required | Implement attachment with valence/chemical validity checks; test generated structures. |

#### MF-15 — Protein structure search is broken

| Field | Value |
|---|---|
| Phase | 4 |
| Severity | **HIGH** |
| Status | Broken |
| Evidence | Product POSTs to `data.rcsb.org/rest/v1/core/search` (HTTP 404); documented endpoint returns 200/323 hits. |
| Impact | Search by accession fails. |
| Required | Use `https://search.rcsb.org/rcsbsearch/v2/query`; add contract test. |

#### MF-16 — Gene Identification is broken

| Field | Value |
|---|---|
| Phase | 4 |
| Severity | **HIGH** |
| Status | Broken |
| Evidence | `NameError: name 'response' is not defined` at `api_clients.py:338`. |
| Impact | Core lookup page unusable. |
| Required | Fix the variable/flow; add a live contract test. |

#### MF-17 — External clients are retired or out of date

| Field | Value |
|---|---|
| Phase | 4–6 |
| Severity | **HIGH** |
| Status | Broken |
| Evidence | Open Targets removed fields → HTTP 400; UniProt `uploadlists` retired → `{}`; ChEMBL `get_target_bioactivities` missing; PDB search endpoint wrong. |
| Impact | Multiple integrations cannot complete a request. |
| Required | Update endpoints/fields; add scheduled live contract tests with recorded fixtures. |

#### MF-18 — Laboratory information management is absent

| Field | Value |
|---|---|
| Phase | 6 |
| Severity | **HIGH** |
| Status | Missing |
| Evidence | The project’s own Phase 6 status lists laboratory management as not implemented; no LIMS subsystem among the 34 `geneai/` directories; only a basic `lab.py` sample register exists. |
| Impact | Cannot manage specimens, protocols, instruments, runs, QC, or chain of custody. |
| Required | Sample lifecycle, protocol/run tracking, instrument/QC records, access control, audit trail. |
| Note | The basic sample register (`add_sample`, `get_lab_stats`) works and should be preserved as a starting point. |

#### MF-19 — Data management and lineage are absent

| Field | Value |
|---|---|
| Phase | 6 |
| Severity | **HIGH** |
| Status | Missing |
| Evidence | Phase 6 status lists data management as not implemented; no dataset registry, checksum, schema migration, retention, or lineage layer found. |
| Impact | Inputs/outputs cannot be versioned, reproduced, or governed. |
| Required | Dataset registry, immutable snapshots, checksums, lineage graph, retention/deletion policy. |

#### MF-20 — Formal QA/validation framework is absent

| Field | Value |
|---|---|
| Phase | 6 |
| Severity | **HIGH** |
| Status | Missing |
| Evidence | Phase 6 status lists QA as not implemented; no validation plan, acceptance criteria, deviation tracking, or qualification records found. |
| Impact | No evidence that scientific/software changes are controlled. |
| Required | Validation plan, traceability matrix, change control, deviation/CAPA process, periodic review. |

---

### 2.2 Security and access

#### MF-21 — No authentication/authorization gate in the main app

| Field | Value |
|---|---|
| Phase | 7 |
| Severity | **CRITICAL** |
| Status | Missing |
| Evidence | Streamlit entry point does not enforce login; multi-user module is not wired at the boundary. |
| Impact | Anyone who can reach the app can use all features/data. |
| Required | AuthN, session management, RBAC, tenant isolation, secure cookie settings, logout/timeout. |

#### MF-22 — No secret management

| Field | Value |
|---|---|
| Phase | 7 |
| Severity | **CRITICAL** |
| Status | Missing |
| Evidence | Hardcoded demo API key `geneai_demo_key_12345` with read/write/analyze scopes. |
| Impact | Default credential is public and over-privileged. |
| Required | Remove hardcoded key; load secrets from a managed store; rotate; scope least privilege. |

#### MF-23 — REST API network defaults are unsafe

| Field | Value |
|---|---|
| Phase | 7 |
| Severity | **HIGH** |
| Status | Broken default |
| Evidence | Binds `0.0.0.0:5000` by default. |
| Impact | Exposes the API on all interfaces. |
| Required | Bind `127.0.0.1` by default; require explicit opt-in for external binding; TLS/reverse proxy guidance. |

#### MF-24 — API key storage is weak

| Field | Value |
|---|---|
| Phase | 7 |
| Severity | **HIGH** |
| Status | Partial |
| Evidence | Keys held in memory; stored as unsalted SHA-256. |
| Impact | Keys disappear on restart and are vulnerable to offline guessing if the store leaks. |
| Required | Persistent store, keyed hashing (e.g. HMAC/PBKDF2/Argon2), prefix lookup, expiry/rotation, revocation. |

#### MF-25 — Multi-user isolation is not enforced

| Field | Value |
|---|---|
| Phase | 7 |
| Severity | **HIGH** |
| Status | Partial |
| Evidence | Multi-user primitives exist; no enforcement at app/API/data boundaries was verified. |
| Impact | Cross-user data exposure risk. |
| Required | Tenant-scoped queries, object-level authorization, tests for cross-tenant access. |

---

### 2.3 Operations and reliability

#### MF-26 — No verified health/readiness endpoint

| Field | Value |
|---|---|
| Phase | 7 |
| Severity | **HIGH** |
| Status | UNVERIFIED / Missing |
| Evidence | No health/readiness check was found or exercised; deployment was not run. |
| Impact | Orchestrators cannot determine service health. |
| Required | `/healthz` and `/readyz` with dependency checks; startup self-test. |

#### MF-27 — No monitoring/alerting

| Field | Value |
|---|---|
| Phase | 7 |
| Severity | **HIGH** |
| Status | Missing |
| Evidence | No metrics/tracing/alerting integration verified. |
| Impact | Failures and performance regressions are invisible. |
| Required | Metrics, structured logs, traces, dashboards, alerts, SLOs. |

#### MF-28 — No backup/restore or disaster recovery

| Field | Value |
|---|---|
| Phase | 7 |
| Severity | **HIGH** |
| Status | UNVERIFIED / Missing |
| Evidence | No backup/restore procedure or test was found. |
| Impact | Data loss risk. |
| Required | Automated backups, restore drills, RPO/RTO targets, encryption. |

#### MF-29 — No audit trail

| Field | Value |
|---|---|
| Phase | 6–7 |
| Severity | **HIGH** |
| Status | Missing |
| Evidence | No immutable record of who ran which analysis/changed which record was verified. |
| Impact | Cannot investigate incidents or support regulated work. |
| Required | Append-only audit log with actor, action, object, timestamp, before/after, correlation ID. |

#### MF-30 — Cloud providers beyond local storage are not implemented/verified

| Field | Value |
|---|---|
| Phase | 5–7 |
| Severity | **MEDIUM** |
| Status | Partial / UNVERIFIED |
| Evidence | `boto3`, GCP, and Azure SDKs absent; 28 cloud tests fail on API drift. |
| Impact | Cloud claims are unsupported. |
| Required | Provider adapters, credential handling, integration tests, or remove cloud claims. |

#### MF-31 — Database performance and cache layers fail budgets

| Field | Value |
|---|---|
| Phase | 5–7 |
| Severity | **HIGH** |
| Status | Broken |
| Evidence | Bulk insert 15.98 s vs 5 s; query 3.98 s vs 2 s; `MultiLevelCache` path `None`; `AsyncCache` returns coroutine. |
| Impact | Poor scalability and unreliable caching. |
| Required | Fix schema/indices/cache init; add performance regression gates. |

#### MF-32 — Clinical-trial persistence is broken

| Field | Value |
|---|---|
| Phase | 4–5 |
| Severity | **HIGH** |
| Status | Broken |
| Evidence | `sqlite3.OperationalError: 26 values for 25 columns`. |
| Impact | Trial records cannot be stored/searched. |
| Required | Align schema and insert; migration + test. |

---

### 2.4 Product and UX honesty

#### MF-33 — Dead sidebar routes

| Field | Value |
|---|---|
| Phase | 1–7 |
| Severity | **HIGH** |
| Status | Broken |
| Evidence | “Disease-Associated Genes” and “Mutation Analysis” have no route; both render Overview silently. |
| Impact | Users are misled about what they are viewing. |
| Required | Implement the pages or remove the entries; never fall through silently. |

#### MF-34 — Placeholder pages presented as features

| Field | Value |
|---|---|
| Phase | 5–7 |
| Severity | **HIGH** |
| Status | Placeholder |
| Evidence | Research Projects, Recent Activities, Research Papers, Research Dashboard, Saved Results, Analysis Statistics. |
| Impact | Inflates apparent completeness. |
| Required | Implement or mark “not available”; remove from primary navigation. |

#### MF-35 — 21 implemented modules are unreachable

| Field | Value |
|---|---|
| Phase | 4–7 |
| Severity | **HIGH** |
| Status | Navigation gap |
| Evidence | Routes exist without sidebar entries (ADMET, Safety, Docking, Design, Genomic/Protein Intelligence, Multi-Agent, Cloud, REST API, etc.). |
| Impact | Most Phase 4–7 functionality is invisible. |
| Required | Add navigation with capability/status labels; or remove dead routes. |

#### MF-36 — Dashboard metrics/activity are fabricated

| Field | Value |
|---|---|
| Phase | 5–7 |
| Severity | **HIGH** |
| Status | Fabricated |
| Evidence | `active_projects + 3`, `completed + 5`, `active_projects + 2`, hardcoded “+2 this week”, five hardcoded activities. |
| Impact | Users cannot distinguish real from invented activity. |
| Required | Derive from stored events; show “no activity” when none exists. |

#### MF-37 — Report citations can be fabricated

| Field | Value |
|---|---|
| Phase | 5–6 |
| Severity | **HIGH** |
| Status | Fabricated content |
| Evidence | DOI `10.5281/zenodo.xxxxxx`; annotation labelled “simulated”. |
| Impact | Research-integrity violation. |
| Required | Verify every citation against a real identifier; remove simulated content; label generated text. |

#### MF-38 — LLM/agent backend is not wired

| Field | Value |
|---|---|
| Phase | 6 |
| Severity | **MEDIUM** |
| Status | Placeholder / UNVERIFIED |
| Evidence | Autonomous planner defaults to `gpt-4` with auto-approve demo; biotech assistant has no backend. |
| Impact | “AI assistant” claims are unsupported; demo autonomy is unsafe if exposed. |
| Required | Provider configuration, prompt/response logging, tool permissions, human approval, evaluation set. |

---

### 2.5 Engineering and test

#### MF-39 — Test suite is not a release gate

| Field | Value |
|---|---|
| Phase | 1–7 |
| Severity | **HIGH** |
| Status | Broken |
| Evidence | 107/502 failures (21.3%). |
| Impact | Regressions cannot be detected reliably. |
| Required | Triage product vs test debt; make the suite green or explicitly xfail with issue links; enforce in CI. |

#### MF-40 — Tests and code are out of sync

| Field | Value |
|---|---|
| Phase | 1–7 |
| Severity | **HIGH** |
| Status | Broken |
| Evidence | Tests patch `api_clients._request` (does not exist); expect missing enum members, workflow methods, cloud constructors. |
| Impact | False failures hide real defects. |
| Required | Align tests with actual boundaries or restore the intended API. |

#### MF-41 — No verified dependency lock/environment matrix

| Field | Value |
|---|---|
| Phase | 7 |
| Severity | **HIGH** |
| Status | Partial |
| Evidence | optuna 5.0.0 vs `<4`; mlflow 3.18 vs `<3`; missing `colorlog`/`slicer`/`yaml`; cloud SDKs absent. |
| Impact | Installations are not reproducible; optional features break unpredictably. |
| Required | Lockfile, supported-version matrix, import smoke tests, extras. |

#### MF-42 — No reproducibility manifest for analyses

| Field | Value |
|---|---|
| Phase | 5–7 |
| Severity | **HIGH** |
| Status | Missing |
| Evidence | No code commit, input checksum, database release, parameters, and model version captured together. |
| Impact | Results cannot be regenerated or defended. |
| Required | Per-analysis manifest and immutable result record. |

#### MF-43 — No reference-genome management

| Field | Value |
|---|---|
| Phase | 2–6 |
| Severity | **MEDIUM** |
| Status | Missing |
| Evidence | VCF normalization is explicitly unverified without a reference FASTA; no reference download/index/version management was found. |
| Impact | REF validation and indel normalization cannot be performed reproducibly. |
| Required | Managed reference bundles (GRCh37/GRCh38) with checksums, indices, and transcript annotations. |

---

## 3. What is not missing

To keep the gap list fair, the following were exercised and worked:

| Capability | Evidence |
|---|---|
| FASTA parsing, length, GC, ambiguous count | Real NCBI `NM_007294.4` and `NM_000546.6` matched `slen` and independently computed GC. |
| VCF parsing, gzip, streaming, multiallelic, symbolic, malformed rejection | Real vcflib VCF + crafted cases. |
| Evidence-preserving mutation interpretation | UI scan; explicit “no classification”. |
| ClinVar retrieval | `rs80357906` → `VCV000017677`, Pathogenic, expert panel. |
| PubMed retrieval | Real PMIDs. |
| PDB entry + AlphaFold fallback | `1M17`; `AF-P04637-F1-model_v6.cif`. |
| Lab sample register | Isolated DB insert/read. |
| Report template honesty | “No automatic citations”. |
| Password hashing | PBKDF2-HMAC-SHA256, 200k, per-user salt, constant-time compare. |

These are real assets and should not be rebuilt from scratch.

---

## 4. Priority view

| Priority | Gaps | Rationale |
|---|---|---|
| **P0 — stop harm/misrepresentation** | MF-01 (claims), MF-02, MF-03, MF-06, MF-10, MF-21, MF-22, MF-23, MF-33, MF-36, MF-37 | Security exposure, fabricated evidence, unusable flagship, unsafe defaults. |
| **P1 — restore truth and basic function** | MF-04, MF-05, MF-07, MF-15, MF-16, MF-17, MF-24, MF-32, MF-34, MF-35, MF-39, MF-40, MF-41 | Make advertised features work or clearly unavailable; green test gate. |
| **P2 — build scientific credibility** | MF-08, MF-09, MF-11, MF-12, MF-13, MF-19, MF-20, MF-27, MF-29, MF-42, MF-43 | Real data, validation, provenance, audit. |
| **P3 — operational maturity** | MF-18, MF-25, MF-26, MF-28, MF-30, MF-31, MF-38 | LIMS, tenancy, monitoring, DR, cloud, scale. |

The ordered execution plan, dependencies, and acceptance gates are in `Priority_Improvement_Roadmap.md`.

---

## 5. Explicit non-goals

The following are **not** recommended as next steps and are outside this audit:

- Creating a Phase 8 feature set.
- Adding new model families before one existing model is validated.
- Expanding the UI before dead routes/placeholders are fixed.
- Claiming clinical utility, regulatory compliance, or production readiness without the controls above.
- Replacing real data gaps with more synthetic/demo content.

---

## 6. Missing-features conclusion

The project does not need more surface area. It needs **truthful labelling, a working prediction path, real data, validated models, and production controls**. The core Phase 1–3 assets are worth preserving; the Phase 4–7 gaps are substantial but bounded. A credible path exists if the work is sequenced as repair → reproducibility → validation → operations, rather than adding new features.

---

*End of Missing Features Report.*
