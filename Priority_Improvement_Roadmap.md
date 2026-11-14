# GeneAI Research — Priority Improvement Roadmap

**Audit date:** 2026-11-13  
**Project:** GeneAI Research, Phases 1–7  
**Purpose:** Ordered, evidence-driven remediation of the findings in the audit; **no Phase 8 features**  
**Companion documents:** `Complete_Audit_Report.md`, `Functional_Test_Report.md`, `Scientific_Validation_Report.md`, `ML_Model_Audit_Report.md`, `Missing_Features_Report.md`

> **Planning rule:** repair before expand. Every item below either removes a harm, makes an advertised Phase 1–7 capability true, or establishes the evidence needed to defend an existing claim. Effort figures are **estimates** (person-days for one experienced engineer/scientist) and must be re-estimated after design review.

---

## 1. Principles

1. **Stop the harm first.** Security exposure, fabricated evidence, and misleading predictions are fixed before new capability.
2. **Truth before features.** Every page must either work, be clearly marked unavailable, or be removed from navigation.
3. **One validated model beats ten unvalidated ones.** Do not add model families until one passes an external validation gate.
4. **Reproducibility is a prerequisite, not a deliverable.** No model result is accepted without data/code/parameter provenance.
5. **Keep the good core.** Sequence/VCF parsing, ClinVar/PubMed retrieval, lab sample register, report templating, and password hashing are assets; do not rewrite them.
6. **No silent fallbacks.** Missing data, missing dependencies, and missing features must surface as explicit states.
7. **Small, verifiable increments.** Each work item ends with an automated or documented acceptance check.

---

## 2. Prioritization method

Each finding was scored on:

| Dimension | Weight | Meaning |
|---|---|---|
| User/scientific harm | 40% | Could the defect cause a wrong decision, false claim, or data exposure? |
| Blocking effect | 25% | Does it prevent a core workflow from running? |
| Security/ethics | 20% | Credential, privacy, integrity, or safety impact? |
| Effort/leverage | 15% | How much credibility is restored per unit of work? |

Resulting bands:

- **P0 — Immediate (0–3 weeks):** remove critical harm and restore basic truth.
- **P1 — Stabilize (3–8 weeks):** make advertised features work or explicitly unavailable; green test gate.
- **P2 — Validate (8–20 weeks):** real data, reproducible models, scientific validation.
- **P3 — Operationalize (20+ weeks):** security hardening, scale, monitoring, governance.

Timelines overlap; they are sequencing bands, not waterfall phases.

---

## 3. Roadmap at a glance

| Band | Theme | Estimated effort | Exit criterion |
|---|---|---|---|
| **P0** | Stop harm, tell the truth, unblock flagship | 25–40 person-days | Gate 0: no critical exposure, no fabricated content, DTI either works or is clearly disabled |
| **P1** | Stabilize contracts, navigation, tests, performance | 40–70 person-days | Gate 1: every visible feature works or is marked unavailable; suite green on pinned env |
| **P2** | Reproducibility and independent scientific validation | 90–160 person-days | Gate 2/3: one model externally validated; provenance end-to-end; real genomic evidence |
| **P3** | Production operations and governance | 80–160 person-days | Gate 4: auth/RBAC, monitoring, backup/DR, audit, load-tested deployment |

**Total indicative effort:** 235–430 person-days. This is an estimate, not a commitment.

---

## 4. P0 — Immediate (0–3 weeks)

### RM-01 — Remove hardcoded credentials and unsafe network defaults

| Field | Value |
|---|---|
| Findings | SEC-01, SEC-02, SEC-03 |
| Files | `geneai/rest_api/core.py`, API config/entry points |
| Actions | Delete `geneai_demo_key_12345`; require keys from env/secret store; default bind `127.0.0.1`; replace unsalted SHA-256 with keyed hashing; add expiry/rotation/revocation; log key creation/use. |
| Acceptance | No secret in source; API refuses to start without a key in non-dev mode; default bind is loopback; hash scheme documented and tested. |
| Validation | Static secret scan; startup test with/without key; auth tests for read/write/analyze scopes; bind-address test. |
| Effort | 2–4 d |
| Depends on | — |

### RM-02 — Enforce an authentication gate or disable shared deployment

| Field | Value |
|---|---|
| Findings | SEC-04 |
| Files | `app.py`, `geneai/multi_user/` |
| Actions | Wire login/session/RBAC at the Streamlit entry point; if not ready, block non-local deployment and display a clear “single-user local prototype” banner. |
| Acceptance | Unauthenticated users cannot reach analysis/data pages; sessions expire; logout works; role checks enforced server-side. |
| Validation | Browser tests for login, logout, timeout, role denial; cross-user data access tests. |
| Effort | 4–6 d |
| Depends on | RM-01 (secret/session config) |

### RM-03 — Remove fabricated dashboard, conservation, and citation content

| Field | Value |
|---|---|
| Findings | F-14, S-05, S-10 |
| Files | `app.py` (`render_main_dashboard`), `geneai/genomic_intelligence/genomic_ui.py`, `geneai/ai_research_intelligence/advanced_report_generator.py` |
| Actions | Replace `+3/+5/+2` and hardcoded activity with stored events or an explicit empty state; delete random PhastCons or label “synthetic demo”; remove `10.5281/zenodo.xxxxxx`; require resolvable citations or omit. |
| Acceptance | Dashboard shows only real counts/events; no random biological track labelled as data; zero fabricated identifiers. |
| Validation | UI inspection with empty/non-empty DB; grep for placeholder DOI/random track; citation resolver test. |
| Effort | 3–4 d |
| Depends on | — |

### RM-04 — Add a capability/status banner and disable misleading predictions

| Field | Value |
|---|---|
| Findings | S-03, S-07, S-08, S-09, M-03 |
| Files | `app.py`, ADMET/safety/repurposing/DTI pages |
| Actions | At startup, report which models/data are loaded; mark untrained/synthetic/heuristic outputs “not validated”; disable prediction buttons when no artefact exists; remove “pretrained” language. |
| Acceptance | Every prediction surface displays its evidence status; no button produces a score without a model artefact. |
| Validation | UI tests for each status; startup report snapshot. |
| Effort | 3–4 d |
| Depends on | — |

### RM-05 — Fix the DTI dependency and feature contract

| Field | Value |
|---|---|
| Findings | F-01, F-02 |
| Files | `geneai/drug_target_prediction/molecular_descriptors.py`, `ml_models.py`, `prediction_engine.py` |
| Actions | Replace `CalcExactMW` with a supported descriptor or capability check; distinguish “installed but incompatible” from “not installed”; define a single feature schema; serialize schema with the model; validate at inference; add regression tests for 2,076-feature contract. |
| Acceptance | Predictor instantiates with the pinned RDKit; one documented molecule/target produces a score; schema mismatch raises a specific error; no silent slicing/padding. |
| Validation | Unit tests for descriptor availability; end-to-end prediction test; contract test with expected feature names/order. |
| Effort | 4–6 d |
| Depends on | RM-11 (dependency lock) |

### RM-06 — Fix Gene Identification

| Field | Value |
|---|---|
| Findings | F-03 |
| Files | `geneai/drug_discovery/api_clients.py:338` |
| Actions | Fix the undefined `response` reference; add timeout/error handling; return an explicit failure state. |
| Acceptance | `TP53` lookup returns identifiers or a clear API error; no traceback. |
| Validation | Live lookup test; mocked failure test. |
| Effort | 0.5–1 d |
| Depends on | — |

### RM-07 — Fix routes, placeholders, and unreachable modules

| Field | Value |
|---|---|
| Findings | F-08, F-09, F-10 |
| Files | `app.py` (`NAV_CATEGORIES`, routing chain) |
| Actions | Implement or remove “Disease-Associated Genes” and “Mutation Analysis”; mark or remove six placeholder pages; add a navigation section for implemented Phase 4–7 modules with status badges; remove silent fall-through. |
| Acceptance | Every sidebar item maps to a distinct page; no placeholder presented as complete; unreachable modules are reachable or removed. |
| Validation | Route-coverage test (sidebar entry → unique renderer); UI click-through. |
| Effort | 3–5 d |
| Depends on | RM-07 can run in parallel with RM-01..06 |

### RM-08 — Fix clinical-trial persistence

| Field | Value |
|---|---|
| Findings | D-01 |
| Files | `geneai/drug_database/` schema/insert |
| Actions | Align 25/26 column mismatch; add migration; test upsert/search. |
| Acceptance | Insert and search succeed on a fresh and migrated DB. |
| Validation | DB integration test; migration test from the old schema. |
| Effort | 1 d |
| Depends on | — |

### RM-09 — Repair external client contracts

| Field | Value |
|---|---|
| Findings | F-04, F-05, F-06, F-07 |
| Files | `opentargets_client.py`, `chembl_client.py`, `prediction_engine.py`, `protein_intelligence/structure_retriever.py`, `uniprot_client.py` |
| Actions | Update Open Targets fields; add `get_target_bioactivities` or switch training to an existing method; use `search.rcsb.org/rcsbsearch/v2/query`; replace retired UniProt `uploadlists` with the current ID-mapping API; fix `entry_name` parsing. |
| Acceptance | Each client returns a documented live response for a known accession; scheduled contract tests detect drift. |
| Validation | Live tests for `P04637`, `CHEMBL203`, `TP53`, PDB search; recorded fixtures. |
| Effort | 5–8 d |
| Depends on | — |

### RM-10 — Triage the test suite and establish a gate

| Field | Value |
|---|---|
| Findings | T-01, T-02, D-03 |
| Files | `tests/`, CI config |
| Actions | Classify 107 failures as product defect vs test debt; fix product defects; update tests that patch non-existent symbols; mark genuinely unavailable features xfail with issue links; require the suite in CI. |
| Acceptance | Suite green or explicitly xfailed with owners; failure count is zero for supported features. |
| Validation | CI run on pinned environment; no unexplained failures. |
| Effort | 6–10 d |
| Depends on | RM-09 (some failures are API drift) |

### RM-11 — Pin dependencies and add import smoke tests

| Field | Value |
|---|---|
| Findings | D-04, P-03, P-04, P-05 |
| Files | `requirements.txt`, `pyproject.toml`, CI |
| Actions | Produce a lockfile; pin RDKit/Optuna/SHAP/MLflow to tested ranges; add missing transitive deps; add import smoke tests; separate optional extras. |
| Acceptance | Clean install from lockfile; all declared extras import; core imports do not require optional packages. |
| Validation | Clean venv install matrix; import tests; version-report endpoint. |
| Effort | 2–4 d |
| Depends on | — |

### P0 exit gate — Gate 0

- No hardcoded secret, no default public bind, auth gate or explicit local-only mode.
- No fabricated metric, activity, conservation track, or DOI.
- DTI either works end-to-end or is clearly disabled with an accurate reason.
- Gene Identification returns a result or a clean error.
- Every sidebar item maps to a real page or is removed.
- Dependency lock and import tests pass.

**Do not proceed to P1 until Gate 0 is met.**

---

## 5. P1 — Stabilize (3–8 weeks)

### RM-12 — Fix database and cache performance contracts

| Field | Value |
|---|---|
| Findings | P-01, P-02, P-03, P-04, P-05, MF-31 |
| Actions | Add indices/batching for bulk insert; optimize the slow query; fix cache path initialization; make async/sync boundary explicit; correct optimiser/pool semantics. |
| Acceptance | Bulk insert < 5 s; query < 2 s on the benchmark fixture; cache tests pass; async API returns values to sync callers. |
| Validation | Performance tests in CI with stable fixtures; before/after timings. |
| Effort | 5–8 d |
| Depends on | RM-11 |

### RM-13 — Consolidate API clients and error handling

| Field | Value |
|---|---|
| Findings | T-02, T-03, D-02 |
| Actions | One HTTP boundary per domain; introduce the `_request` helper tests expect; normalize timeouts/retries/errors; preserve release/accession metadata; delete duplicate clients. |
| Acceptance | One client per API; contract tests pass; errors are typed and surfaced. |
| Validation | Unit tests with mocked HTTP; live smoke tests. |
| Effort | 6–10 d |
| Depends on | RM-09 |

### RM-14 — Replace silent ML fallbacks with explicit capability states

| Field | Value |
|---|---|
| Findings | S-06, M-01 |
| Actions | Remove NaN/zero feature substitution; report missing feature sources; compute CV mean/std from folds; add tests that fail if std is hardcoded. |
| Acceptance | Prediction blocked when required features are missing; CV report contains real per-fold values. |
| Validation | Missing-feature tests; CV determinism test. |
| Effort | 4–6 d |
| Depends on | RM-05 |

### RM-15 — Fix model-selection leakage

| Field | Value |
|---|---|
| Findings | M-02 |
| Actions | Nested CV or held-out selection set; separate selection and reporting; freeze the final test set. |
| Acceptance | Reported score comes from outer folds/test set only; selection code path documented. |
| Validation | Leakage test: inject a random feature and confirm the reported score does not improve spuriously under the protocol. |
| Effort | 3–5 d |
| Depends on | RM-14 |

### RM-16 — Add honest report generation and citation verification

| Field | Value |
|---|---|
| Findings | S-10, MF-37 |
| Actions | Remove simulated annotation from report bodies; resolve every citation via DOI/PubMed/ClinVar; omit unresolved references; label generated text. |
| Acceptance | No unresolved DOI/PMID; simulated content absent or clearly quarantined. |
| Validation | Citation resolver test; report snapshot review. |
| Effort | 3–4 d |
| Depends on | RM-03 |

### RM-17 — Add reference-genome management and normalization

| Field | Value |
|---|---|
| Findings | MF-43, Scientific UV-03 |
| Actions | Manage GRCh37/GRCh38 FASTA + index + transcript annotation with checksums; add REF validation and left-normalization; expose assembly explicitly. |
| Acceptance | VCF normalization reproduces `bcftools norm` for a documented set; wrong-REF variants are flagged. |
| Validation | Concordance test vs `bcftools norm`; checksum verification. |
| Effort | 6–10 d |
| Depends on | MF-19 (dataset registry) can start in parallel |

### RM-18 — Error boundaries and observability in the app

| Field | Value |
|---|---|
| Findings | Reliability weaknesses (raw tracebacks), MF-26 |
| Actions | Top-level exception boundary with correlation ID; user-safe error messages; structured logs; startup self-test. |
| Acceptance | No raw traceback reaches the UI; every error has a correlation ID; startup reports dependency status. |
| Validation | Fault-injection tests; log inspection. |
| Effort | 4–6 d |
| Depends on | RM-04 |

### RM-19 — Complete or remove placeholder product surfaces

| Field | Value |
|---|---|
| Findings | F-09, F-12, F-13 |
| Actions | Implement Research Projects/Recent Activities/Saved Results from real storage, or remove; fix scaffold substituent attachment; complete or remove integrated-precision stages. |
| Acceptance | No “coming soon” page in primary navigation; molecule generation produces valid modified structures; pipeline stages either run or are absent. |
| Validation | UI route tests; chemistry validity tests; pipeline stage tests. |
| Effort | 8–12 d |
| Depends on | RM-07 |

### P1 exit gate — Gate 1

- Every visible feature works or is explicitly unavailable.
- Test suite green on the pinned environment.
- Performance budgets met on stable fixtures.
- No silent fallback for missing data/dependencies.
- Report citations resolve.
- No raw traceback in the UI.

---

## 6. P2 — Validate (8–20 weeks)

### RM-20 — Build the model reproducibility layer

| Field | Value |
|---|---|
| Findings | S-03, M-04, MF-01, MF-42 |
| Actions | Dataset registry with checksums/licences; feature-schema registry; preprocessing serialization; hyperparameter/seed capture; artefact hashing; model cards; one-command retraining. |
| Acceptance | Retraining from the manifest reproduces the artefact hash and metrics within tolerance. |
| Validation | Clean-room reproduction test; manifest audit. |
| Effort | 10–15 d |
| Depends on | RM-11, RM-13 |

### RM-21 — Validate the DTI model on external data

| Field | Value |
|---|---|
| Findings | S-04, S-11, F-02 |
| Actions | Curate a documented interaction dataset; scaffold/time split; matched decoys; external test; calibration; applicability domain; compare with a baseline. |
| Acceptance | External test metrics with confidence intervals; calibration reported; model card published; limitations documented. |
| Validation | Independent evaluator reruns the frozen model on the held-out set. |
| Effort | 15–25 d |
| Depends on | RM-20, RM-05 |

### RM-22 — Validate mutation ML

| Field | Value |
|---|---|
| Findings | S-06, M-01, M-02, M-03 |
| Actions | Wire real conservation/AlphaMissense/UniProt features; missingness policy; nested CV; calibration; external variant set; compare with a published baseline. |
| Acceptance | External variant evaluation with CIs/calibration; no silent zero-fill; model card. |
| Validation | Independent test set; ablation showing feature contribution. |
| Effort | 15–25 d |
| Depends on | RM-20, RM-14, RM-15 |

### RM-23 — Integrate a validated docking engine

| Field | Value |
|---|---|
| Findings | S-01, S-02, MF-03, MF-04 |
| Actions | Integrate Vina/Smina/GNINA; receptor/ligand preparation; redocking RMSD; enrichment; affinity correlation; expose engine/version/parameters; remove heuristic kcal/mol claims. |
| Acceptance | Redocking success rate reported; scores calibrated/validated; engine provenance visible. |
| Validation | Redock a documented set of co-crystals (RMSD ≤ 2 Å); enrichment on a benchmark; reproduce a published baseline. |
| Effort | 20–30 d |
| Depends on | RM-20 |

### RM-24 — Build real ADMET and toxicity models (or relabel as rules)

| Field | Value |
|---|---|
| Findings | S-07, S-08, MF-05, MF-06 |
| Actions | Choose endpoints with accessible curated data; document labels/licences; train/validate/calibrate; applicability domain; or remove predictive claims and present rules explicitly. |
| Acceptance | Each endpoint has a model card + external test + calibration, or is labelled “rule-based screen”. |
| Validation | External assay set; calibration; comparison with a published baseline. |
| Effort | 20–35 d |
| Depends on | RM-20 |

### RM-25 — Build real genomic association and conservation data

| Field | Value |
|---|---|
| Findings | F-11, S-05, MF-08, MF-09, MF-10 |
| Actions | GWAS Catalog client; ClinVar/Open Targets/HPO association; real PhastCons/phyloP; FDR control; provenance per association. |
| Acceptance | Gene/variant → disease associations return sourced evidence; conservation track is real and versioned. |
| Validation | Compare with documented ClinVar/GWAS records; spot-check conservation values against the source. |
| Effort | 15–25 d |
| Depends on | RM-13 |

### RM-26 — Validate biomarker and repurposing pipelines

| Field | Value |
|---|---|
| Findings | S-09, MF-11, MF-12 |
| Actions | Pre-register pipelines; use independent cohorts; multiple-testing control; retrospective repurposing hit-rate; remove the 0.5 placeholder or justify it; report uncertainty. |
| Acceptance | External validation report for each; no unexplained constants in scoring. |
| Validation | Held-out cohort; retrospective known-indication recovery. |
| Effort | 20–35 d |
| Depends on | RM-20 |

### RM-27 — Data management, provenance, and audit trail

| Field | Value |
|---|---|
| Findings | MF-19, MF-29, MF-42 |
| Actions | Dataset registry; immutable analysis records; lineage graph; append-only audit log; retention/deletion policy. |
| Acceptance | Any result can be traced to inputs, code, parameters, and model version; audit log tamper-evident. |
| Validation | Reconstruct a prior analysis from the record alone; attempt to modify audit log and confirm detection. |
| Effort | 15–25 d |
| Depends on | RM-20 |

### RM-28 — Formal QA/validation framework

| Field | Value |
|---|---|
| Findings | MF-20 |
| Actions | Validation plan; requirements traceability; change control; deviation/CAPA; periodic review. |
| Acceptance | Every change has a risk assessment and test evidence; deviations tracked to closure. |
| Validation | Internal audit of a sample of changes. |
| Effort | 10–15 d |
| Depends on | RM-10, RM-27 |

### P2 exit gate — Gate 2/3

- At least one model has a published external validation report and model card.
- Every model output is traceable to data/code/parameters/artefact.
- No synthetic/placeholder content in user-facing scientific output.
- Docking either validated or explicitly labelled a heuristic.
- Genomic associations use real, sourced evidence.
- QA records exist for the validated scope.

---

## 7. P3 — Operationalize (20+ weeks)

### RM-29 — Production authentication, RBAC, and tenancy

| Field | Value |
|---|---|
| Findings | SEC-04, MF-21, MF-25 |
| Actions | SSO/OIDC or strong local auth; RBAC; tenant-scoped data access; session hardening; admin audit. |
| Acceptance | Cross-tenant access denied; least-privilege roles enforced; auth events audited. |
| Validation | Authorization matrix tests; penetration test. |
| Effort | 15–25 d |
| Depends on | RM-02 |

### RM-30 — Cloud provider implementations

| Field | Value |
|---|---|
| Findings | MF-30, 28 cloud test failures |
| Actions | Implement/repair AWS/GCP/Azure adapters; credential chain; retries/idempotency; integration tests; or remove cloud claims. |
| Acceptance | Upload/download/list/delete round-trip on each supported provider; failure handling verified. |
| Validation | Staging accounts; chaos/failure tests. |
| Effort | 20–35 d |
| Depends on | RM-11, RM-13 |

### RM-31 — Health, monitoring, alerting, and SLOs

| Field | Value |
|---|---|
| Findings | MF-26, MF-27 |
| Actions | `/healthz`, `/readyz`, metrics, traces, dashboards, alerts, SLOs, on-call runbook. |
| Acceptance | A dependency failure is visible within the alert window; readiness reflects DB/API state. |
| Validation | Fault injection; alert drill. |
| Effort | 10–15 d |
| Depends on | RM-18 |

### RM-32 — Backup, restore, and disaster recovery

| Field | Value |
|---|---|
| Findings | MF-28 |
| Actions | Automated encrypted backups; restore drills; RPO/RTO; documented runbook. |
| Acceptance | Restore into a clean environment within RTO; data integrity verified. |
| Validation | Scheduled restore drill; checksum comparison. |
| Effort | 8–12 d |
| Depends on | RM-27 |

### RM-33 — Scale and load testing

| Field | Value |
|---|---|
| Findings | Performance/scalability gaps |
| Actions | Load test ingestion, VCF analysis, DB, and API; profile bottlenecks; set capacity limits. |
| Acceptance | Documented throughput/latency at target concurrency; no unbounded memory growth. |
| Validation | Repeatable load test in CI/staging. |
| Effort | 10–15 d |
| Depends on | RM-12, RM-31 |

### RM-34 — Laboratory information management (Phase 6)

| Field | Value |
|---|---|
| Findings | MF-18 |
| Actions | Extend the working sample register into specimen lifecycle, protocols/runs, instruments, QC, chain of custody, access control. |
| Acceptance | Sample → aliquot → run → result chain is traceable; QC states enforced. |
| Validation | End-to-end lab workflow test; audit reconstruction. |
| Effort | 20–35 d |
| Depends on | RM-27, RM-29 |

### RM-35 — Model registry, drift monitoring, and revalidation

| Field | Value |
|---|---|
| Findings | M-03, S-11, MF-01 |
| Actions | Registry with stage transitions/rollback; input drift; performance monitoring; periodic revalidation and retirement. |
| Acceptance | Every production prediction references a registered model version; drift alert triggers review. |
| Validation | Simulated drift; rollback drill. |
| Effort | 12–20 d |
| Depends on | RM-20, RM-31 |

### RM-36 — Security and privacy hardening

| Field | Value |
|---|---|
| Findings | SEC-01..04, MF-21..25 |
| Actions | Threat model; dependency/SAST scanning; secret scanning; authorization tests; privacy review (GDPR/HIPAA if applicable); incident response. |
| Acceptance | No critical/high findings in an authorized assessment; documented privacy posture. |
| Validation | Third-party penetration test; privacy impact assessment. |
| Effort | 15–25 d |
| Depends on | RM-29, RM-31 |

### P3 exit gate — Gate 4

- Auth/RBAC/tenancy enforced and tested.
- Health/monitoring/alerting/backup/DR verified by drill.
- Load targets met.
- Model registry and drift monitoring live.
- Security assessment with no unresolved critical/high issues for the claimed scope.
- Claims match evidence; no Phase 8 scope creep.

---

## 8. Sequencing and dependencies

```
P0  RM-01 ─┬─ RM-02
    RM-03  │
    RM-04  │
    RM-11 ─┼─ RM-05 ── RM-14 ── RM-15 ── RM-22
    RM-06  │
    RM-07  │
    RM-08  │
    RM-09 ─┴─ RM-13 ── RM-25
    RM-10

P1  RM-12  RM-16  RM-17  RM-18  RM-19
    (RM-12 depends on RM-11; RM-16 on RM-03; RM-10 on RM-09)

P2  RM-20 ─┬─ RM-21
           ├─ RM-22
           ├─ RM-23
           ├─ RM-24
           ├─ RM-26
           └─ RM-27 ── RM-28
    RM-25 (depends on RM-13)

P3  RM-29 ─┬─ RM-34
           └─ RM-36
    RM-31 ── RM-35
    RM-32  RM-33  RM-30
```

**Critical path:** RM-11 → RM-05 → RM-14/15 → RM-20 → RM-21/22 → RM-27 → RM-29/31 → RM-36.

**Parallelizable early:** RM-01/02 security, RM-03 honesty, RM-06/07/08 quick fixes, RM-09 API repair, RM-17 reference genome.

---

## 9. Traceability matrix

| Finding | Roadmap item(s) |
|---|---|
| F-01 | RM-05 |
| F-02 | RM-05, RM-21 |
| F-03 | RM-06 |
| F-04 | RM-09 |
| F-05 | RM-09 |
| F-06 | RM-09 |
| F-07 | RM-09 |
| F-08 | RM-07 |
| F-09 | RM-07, RM-19 |
| F-10 | RM-07 |
| F-11 | RM-25 |
| F-12 | RM-19 |
| F-13 | RM-19 |
| F-14 | RM-03 |
| S-01 | RM-23 |
| S-02 | RM-23 |
| S-03 | RM-04, RM-20 |
| S-04 | RM-21 |
| S-05 | RM-03, RM-25 |
| S-06 | RM-14, RM-22 |
| S-07 | RM-24 |
| S-08 | RM-24 |
| S-09 | RM-26 |
| S-10 | RM-03, RM-16 |
| S-11 | RM-21/22/24/26, RM-35 |
| M-01 | RM-14 |
| M-02 | RM-15 |
| M-03 | RM-22, RM-24, RM-35 |
| M-04 | RM-20 |
| SEC-01 | RM-01 |
| SEC-02 | RM-01 |
| SEC-03 | RM-01 |
| SEC-04 | RM-02, RM-29 |
| P-01 | RM-12 |
| P-02 | RM-12 |
| P-03 | RM-12 |
| P-04 | RM-12 |
| P-05 | RM-12 |
| D-01 | RM-08 |
| D-02 | RM-13 |
| D-03 | RM-10, RM-30 |
| D-04 | RM-11 |
| T-01 | RM-10 |
| T-02 | RM-10, RM-13 |
| T-03 | RM-13 |
| MF-01..MF-43 | Mapped throughout RM-01..RM-36; see §4–7 |
| UV-01 | RM-17 (reference), plus a CDS validation task under RM-22 |
| UV-02 | Add FASTQ validation to RM-17/22 scope |
| UV-03 | RM-17 |
| UV-04..UV-10 | RM-21/22/23/24/26 |
| UV-11 | RM-19, RM-26 |
| UV-12 | RM-16, add agent evaluation under RM-38-equivalent (P3 scope) |
| UV-13 | Out of scope until regulatory program exists |
| UV-14 | RM-30, RM-31, RM-33 |
| UV-15 | RM-36 |

---

## 10. Effort assumptions

| Assumption | Effect if wrong |
|---|---|
| One experienced engineer/scientist at ~70% focus | Timeline stretches proportionally |
| Access to public data and a staging cloud account | P2/P3 cloud/model work blocked |
| Product owner empowered to remove/hide features | Honesty work becomes slower and politically harder |
| No requirement for clinical/regulatory use in this cycle | If required, add 6–12 months and formal QMS |
| Existing Phase 1–3 code retained | Rewriting adds significant effort |

**These are planning estimates, not guarantees.** Re-estimate after a design spike for RM-20 (reproducibility) and RM-23 (docking), which carry the largest uncertainty.

---

## 11. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Attempt to “fix” DTI by padding/truncating features | Medium | Critical | Enforce schema validation; code review; contract test |
| Synthetic/demo data leaks back into user-facing claims | Medium | Critical | Capability banner; model cards; content review |
| Security fix breaks local demo convenience | Medium | Medium | Explicit local-only mode with warning |
| API providers change again | High | Medium | Scheduled contract tests; fixtures; version pinning |
| Model validation finds no signal | Medium | High | Report honestly; do not ship; pivot to rules/heuristics |
| Docking integration consumes schedule | High | High | Time-box; fall back to “not available” labelling |
| Scope creep into Phase 8 | High | High | Gate reviews; this roadmap as scope contract |
| No owner for data licences | Medium | High | Assign data steward before RM-20 |
| Users rely on outputs before fixes land | Medium | Critical | Immediate banner/disablement in RM-03/RM-04 |

---

## 12. Definition of done

A work item is done only when:

1. The code change is merged with a test that fails before and passes after.
2. The user-facing status matches reality (works / unavailable / demo / heuristic).
3. No fabricated, synthetic, or placeholder content is presented as real.
4. Provenance is captured for any scientific output.
5. Documentation and the capability banner are updated.
6. The full test suite passes on the pinned environment.
7. A reviewer other than the author has checked the evidence.

A **phase** is done only when its exit gate is met and the claims in `PHASE_1_TO_7_STATUS.md` (or its replacement) are edited to match the evidence.

---

## 13. What not to do

- Do **not** start Phase 8.
- Do **not** add new model families before one model is externally validated.
- Do **not** add new UI pages before dead routes and placeholders are fixed.
- Do **not** replace missing real data with more synthetic data.
- Do **not** describe the platform as “production-ready”, “clinical”, or “validated” until Gate 4 and the relevant external validation are complete.
- Do **not** use test pass rate alone as a quality signal; the suite itself is being repaired.

---

## 14. First 10 working days

| Day | Work |
|---|---|
| 1–2 | RM-01: remove hardcoded key, loopback bind, key hashing; RM-03: remove fake dashboard/DOI/random track. |
| 3–4 | RM-06: Gene ID fix; RM-08: clinical-trial schema; RM-07: route inventory and dead-route removal. |
| 5 | RM-04: capability banner + disable untrained predictions; publish interim “known limitations” notice. |
| 6–7 | RM-11: dependency lock + import smoke tests; start RM-05 descriptor/schema fix. |
| 8–9 | RM-05: DTI end-to-end on one molecule/target; RM-09: PDB/UniProt/Open Targets/ChEMBL contract fixes. |
| 10 | RM-10: triage 107 failures into product vs test debt; Gate 0 review. |

**Gate 0 review at day 10.** If Gate 0 is not met, extend P0 rather than starting P1.

---

## 15. Final recommendation

The correct next move is **not** to expand the platform. It is to make the existing Phases 1–7 truthful, secure, reproducible, and scientifically defensible in that order. The Phase 1–3 core is worth keeping; the Phase 4–7 surface needs repair and validation, not more features. If the team executes P0 and P1 faithfully, the project can credibly become a research-grade workbench. P2 determines whether it can make scientific claims. P3 determines whether it can be operated by more than one trusted user.

---

*End of Priority Improvement Roadmap.*
