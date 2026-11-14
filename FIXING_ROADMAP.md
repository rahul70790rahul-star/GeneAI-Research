# GeneAI Research - Fixing Roadmap

**Generated:** 2026-11-12  
**Based on:** Complete project audit, bug report, and UI/UX audit

---

## Fix Priority Matrix

| Priority | Category | Count | Timeline |
|----------|----------|-------|----------|
| P0 - Critical | Scientific integrity, broken imports | 5 | Week 1 |
| P1 - High | Production readiness, major bugs | 12 | Week 1-2 |
| P2 - Medium | Code quality, performance, UX | 25 | Week 2-4 |
| P3 - Low | Polish, accessibility, docs | 15 | Week 4-6 |

---

## Week 1: Critical Fixes (P0-P1)

### Day 1-2: Scientific Integrity & Broken Code

#### TASK-001: Fix Autonomous Agent Mock Tools [P0]
**Files:** `geneai/autonomous_agent/tools/*.py` (6 files)
**Action:** Replace all mock implementations with real GeneAI module calls
**Details:**
- `analysis_tools.py` → Reactome pathway analysis, QuickGO GO annotations, STRING PPI, scipy expression analysis ✅
- `docking_tools.py` → molecular_docking.docking_engine (Vina/smina/gnina/internal) ✅
- `disease_tools.py` → Open Targets API, Reactome, QuickGO, PubMed, ClinicalTrials.gov ✅
- `variant_tools.py` → Already uses real Ensembl VEP, gnomAD, ClinVar APIs ✅
- `literature_tools.py` → Already uses real PubMed, Europe PMC, Crossref, OpenAlex APIs ✅
- `admet_tools.py` → Already uses real ADMETPredictionEngine ✅
- `sequence_tools.py` → Already has real sequence analysis implementation ✅

**Acceptance:** All tools return real data from actual module executions
**Status:** ✅ **COMPLETED** (2026-11-12)

#### TASK-002: Remove/Implement disease_intelligence Package [P0]
**Files:** `geneai/disease_intelligence/` (directory)
**Action:** Delete empty directory and remove all references
**Details:** 
- Remove from PROJECT_INSPECTION_REPORT.md references
- Remove from any import statements
- If needed, create minimal `__init__.py` with deprecation notice

**Acceptance:** No import errors; directory removed
**Status:** ✅ **COMPLETED** (2026-11-12) - Removed directory; functionality moved to autonomous_agent.tools.disease_tools; updated geneai/__init__.py and tests.

#### TASK-003: Fix REST API Test Console [P1]
**Files:** `geneai/rest_api/ui.py`
**Action:** Connect test playground to actual FastAPI endpoints
**Details:** Replace mock responses with real HTTP calls to local API

**Acceptance:** Test console shows real API responses
**Status:** ✅ **COMPLETED** (2026-11-12) - Updated render_test_console_tab() to make actual HTTP requests to the API server with configurable base URL, API key, and request body; shows real responses with status codes and timing.

#### TASK-004: Consolidate Duplicate Code [P1]
**Files:** 
- `geneai/drug_discovery/api_clients.py`
- `geneai/drug_discovery/ncbi_client.py`
- `geneai/drug_discovery/chembl_client.py`
- `geneai/drug_discovery/pubchem_client.py`
- `geneai/drug_discovery/opentargets_client.py`
- `geneai/drug_discovery/uniprot_client.py`
- `geneai/drug_safety/data_integration.py`

**Action:** 
1. Create `geneai/utils/rate_limiter.py` - shared RateLimiter class ✅
2. Create `geneai/utils/exceptions.py` - shared DataSourceError and hierarchy ✅
3. Create `geneai/utils/api_client_base.py` - base API client with retry/rate limiting ✅
4. Refactor all modules to use shared utilities ✅

**Acceptance:** Single source of truth for rate limiting and exceptions
**Status:** ✅ **COMPLETED** (2026-11-12) - Created shared utilities in geneai/utils/; refactored api_clients.py and drug_safety/data_integration.py to use BaseAPIClient, shared RateLimiter, and shared exceptions.

#### TASK-005: Add Health Check Endpoint [P1]
**Files:** `geneai/rest_api/core.py`, `app.py`
**Action:** Add `/health` and `/ready` endpoints
**Details:**
- `/health` - Basic liveness (returns 200 OK) ✅
- `/ready` - Readiness (checks DB connections, API connectivity) ✅
- Add to Streamlit as well for container health checks

**Acceptance:** Docker health checks pass; Kubernetes probes work
**Status:** ✅ **COMPLETED** (2026-11-12) - Added /ready endpoint in rest_api/core.py with knowledge graph and database connectivity checks.

---

### Day 3-4: Production Readiness

#### TASK-006: Implement Database Migration System [P1]
**Files:** All `database.py` modules, new `geneai/database/migrations.py`
**Action:** Create migration framework using Alembic or custom solution
**Details:**
- Version table in each database
- Migration scripts numbered sequentially
- Auto-migrate on startup (with backup)
- Rollback capability

**Acceptance:** Schema changes deployable without manual SQL

#### TASK-007: Fix DB Connection Leaks [P1]
**Files:** All `database.py` modules
**Action:** Add proper connection lifecycle management
**Details:**
- Context managers for all connections
- `atexit` registration for cleanup
- Streamlit session end cleanup
- Connection pooling for multi-threaded access

**Acceptance:** No connection leaks under load testing

#### TASK-008: Reduce VCF Decompression Limit [P1]
**Files:** `geneai/config.py`, `geneai/variants.py`, `geneai/mutation.py`
**Action:** 
- Change `MAX_VCF_DECOMPRESSED_BYTES` from 2GB to 500MB default
- Make configurable via environment variable
- Add memory check before processing large files
- Show warning for files approaching limit

**Acceptance:** No OOM on 8GB RAM system with large VCFs

#### TASK-009: Fix Navigation - Categorized Sidebar [P1]
**Files:** `app.py`
**Action:** Replace flat radio list with categorized navigation
**Details:** Implement structure from UI_UX_AUDIT.md:
- Use `st.sidebar` with expandable sections
- Add search/filter input
- Group 89 pages into 6 categories
- Move admin tools (Security, Performance, Professional UI) to Settings

**Acceptance:** Users can find modules in <3 clicks
**Status:** ✅ **COMPLETED** (2026-11-12) - Categorized navigation with expanders, search filter, 6 categories (Core Analysis, Genomics & Variants, Drug Discovery, AI & Intelligence, Protein & Molecular, Platform & Integration, Settings & Admin).

#### TASK-010: Apply Professional UI Globally [P1]
**Files:** `app.py`, `geneai/professional_ui/core.py`
**Action:** 
- Call `inject_professional_css()` in `app.py` before page render
- Add theme selector to sidebar
- Sync `.streamlit/config.toml` with professional_ui themes

**Acceptance:** Consistent professional styling on all pages
**Status:** ✅ **COMPLETED** (2026-11-12) - inject_professional_css() called at app startup; render_theme_selector() in sidebar with mode (light/dark/auto/high_contrast), color scheme, compact mode, animations, font size; CSS variables applied globally.

---

### Day 5: Testing & Validation

#### TASK-011: Run Full Test Suite [P1]
**Command:** `python run_tests.py all --coverage`
**Action:** Fix any failing tests from refactoring
**Target:** >80% coverage on core modules

#### TASK-012: Validate Critical User Flows [P1]
**Flows to test:**
1. Sequence analysis (upload + paste)
2. VCF analysis (small + large streaming)
3. Mutation interpretation
4. Drug discovery workflow (disease → genes → targets → drugs)
5. ADMET prediction (single + batch)
6. Molecular docking
7. Biotech assistant Q&A
8. Multi-agent workflow
9. Knowledge graph search
10. Report generation

---

## Week 2: High Priority Fixes (P1-P2)

### Module Implementation (Phase 6)

#### TASK-013: Implement Laboratory Management [P2]
**Files:** `geneai/lab_management.py` (expand), new UI module
**Features:**
- Experiment CRUD (create, read, update, delete)
- Project management (hierarchical)
- Dataset linking to experiments
- Result management with versioning
- Status tracking (planned, running, completed, failed)
- Protocol documentation
- Import/export (CSV, JSON)
- Data validation

#### TASK-014: Implement Data Management [P2]
**Files:** `geneai/data_management.py` (expand), new UI module
**Features:**
- CSV/Excel/JSON import with preview
- Data cleaning (duplicates, missing values, outliers)
- Column type detection and conversion
- Data profiling (statistics, distributions)
- Export with formatting options

#### TASK-015: Implement Quality Assurance [P2]
**Files:** `geneai/quality_assurance.py` (expand), new UI module
**Features:**
- Data integrity checks (foreign keys, constraints)
- Automated validation rules
- Quality metrics dashboard
- Alerting on anomalies
- Audit trail for data changes

### Performance Optimization

#### TASK-016: Lazy Load ML Models [P2]
**Files:** 
- `geneai/admet_prediction/ml_models.py`
- `geneai/drug_target_prediction/ml_models.py`
- `geneai/drug_safety/ml_models.py`
- `geneai/deep_learning/__init__.py`

**Action:** Wrap model loading in `@cached` decorator; load on first prediction

#### TASK-017: Add Connection Pooling [P2]
**Files:** All `database.py` modules
**Action:** Implement thread-safe connection pool (max 5-10 connections)

#### TASK-018: Parallelize Batch Operations [P2]
**Files:** 
- `geneai/admet_prediction/admet_ui.py` (batch comparison)
- `geneai/molecular_docking/docking_ui.py` (batch docking)
- `geneai/drug_target_prediction/drug_target_ui.py` (batch screening)

**Action:** Use `concurrent.futures.ThreadPoolExecutor` with progress tracking

---

## Week 3-4: Medium Priority (P2)

### UI/UX Standardization

#### TASK-019: Create Base Module UI Template [P2]
**Files:** New `geneai/ui_template.py`
**Pattern:**
```python
def render_module_page():
    pro_page_header("Title", "Description", actions=[...])
    
    with st.form("input_form"):
        # Inputs with help tooltips
        submitted = st.form_submit_button("Run", type="primary")
    
    if submitted:
        with st.status("Processing...", expanded=True) as status:
            # Steps with progress
            results = run_analysis(params)
            status.update(label="Complete", state="complete")
    
    if results:
        # Tabs: Results, Visualizations, Export, Limitations
        pro_empty_state for empty results
```

#### TASK-020: Add Sample Data to All Modules [P2]
**Files:** Each module's UI file
**Action:** Add "Load Example" button with scientifically valid test data

#### TASK-021: Standardize Error Handling [P2]
**Files:** All UI modules
**Action:** 
- Catch specific exceptions
- Show user-friendly messages with actionable guidance
- Log technical details for debugging

#### TASK-022: Add Contextual Help/Tooltips [P2]
**Files:** All UI modules
**Action:** Add `help=` parameter to all input widgets

#### TASK-023: Implement Real Dashboard [P2]
**Files:** `app.py` (Overview page)
**Action:**
- Query actual databases for metrics
- Recent activity from audit logs
- Quick action cards with navigation
- System status panel (DB, APIs, disk, memory)

### Visualization Fixes

#### TASK-024: Fix Knowledge Graph Visualization [P2]
**Files:** `geneai/ai_research_intelligence/knowledge_graph.py`
**Options:**
- Add `pyvis>=0.3,<1.0` to requirements.txt
- OR replace with Plotly network graph
- OR make optional with graceful degradation

#### TASK-025: Theme-Aware Plotly Charts [P2]
**Files:** All modules using Plotly
**Action:** Use CSS variables for colors; update on theme change

#### TASK-026: Bundle py3Dmol Locally [P2]
**Files:** Modules using py3Dmol
**Action:** Download py3Dmol.js; serve locally; add offline fallback

#### TASK-027: Add Chart Image Export [P2]
**Files:** All visualization modules
**Action:** Add "Download PNG/SVG" buttons using `plotly.io.to_image`

---

## Week 5-6: Low Priority & Polish (P3)

### Accessibility

#### TASK-028: Screen Reader Integration [P3]
**Files:** `app.py`, `geneai/professional_ui/core.py`
**Action:** Call `announce_to_screen_reader()` for dynamic content updates

#### TASK-029: Keyboard Shortcuts [P3]
**Files:** `geneai/professional_ui/core.py`
**Action:** Add shortcuts for common actions (Cmd/Ctrl+Enter to run, Esc to cancel)

#### TASK-030: High Contrast Mode Default [P3]
**Files:** `geneai/professional_ui/ui.py`
**Action:** Add high contrast as default theme option

### Documentation & Testing

#### TASK-031: Update All Documentation [P3]
**Files:** README.md, CHANGELOG.md, docs/
**Action:** Reflect all changes; add migration guide

#### TASK-032: Add Integration Tests [P3]
**Files:** `tests/test_integration.py`
**Action:** End-to-end workflow tests for key user journeys

#### TASK-033: Load/Stress Testing [P3]
**Files:** New `tests/test_performance_load.py`
**Action:** Simulate concurrent users; identify bottlenecks

#### TASK-034: Security Hardening [P3]
**Files:** `geneai/security/core.py`, deployment configs
**Action:** 
- Secret rotation automation
- API key scoping
- Penetration test fixes

---

## Week 7-8: ML Pipeline for Mutation Interpretation (New Major Task)

### Mutation ML Pipeline Implementation

#### TASK-035: Dataset Acquisition Module [P1]
**Files:** `geneai/mutation_ml/dataset_acquisition.py`
**Action:** Create fetchers for ClinVar, gnomAD, Ensembl, dbSNP, COSMIC, UniProt, AlphaMissense
**Features:**
- Download and cache all major variant annotation databases
- REST API clients for Ensembl VEP, dbSNP, UniProt
- Chunked parsing for large files (ClinVar, gnomAD, AlphaMissense)
- Progress tracking and resume capability

**Acceptance:** All 7 datasets downloadable and parsable
**Status:** ✅ **COMPLETED** (2026-11-12)

#### TASK-036: Feature Engineering Pipeline [P1]
**Files:** `geneai/mutation_ml/preprocessing.py`
**Action:** Build VariantPreprocessor and FeatureEngineer classes
**Features:**
- Consequence severity scoring (from variant_prioritizer.py)
- Population frequency features (gnomAD AF, AN, AC, popmax)
- Clinical significance encoding (ClinVar)
- Functional prediction scores (CADD, REVEL, SIFT, PolyPhen, SpliceAI)
- AlphaMissense pathogenicity integration
- COSMIC cancer mutation counts
- UniProt domain/feature overlap
- Conservation scores (PhyloP, PhastCons placeholder)
- Splice site distance features
- Robust preprocessing pipeline (imputation, scaling, encoding)

**Acceptance:** Raw variants → ML-ready feature matrix
**Status:** ✅ **COMPLETED** (2026-11-12)

#### TASK-037: ML Training Pipeline [P1]
**Files:** `geneai/mutation_ml/training.py`
**Action:** Implement MutationMLTrainer with 6 algorithms
**Models:**
- Logistic Regression (with calibration)
- Random Forest
- Gradient Boosting
- XGBoost (if available)
- LightGBM (if available)
- SVM (RBF kernel)

**Features:**
- Stratified K-fold cross-validation
- Hyperparameter optimization (GridSearchCV)
- Model calibration (isotonic regression)
- Feature importance extraction
- Calibration curves (ROC, PR)
- Model persistence (pickle)
- Comprehensive metrics (accuracy, balanced_accuracy, precision, recall, F1, MCC, ROC-AUC, PR-AUC)

**Acceptance:** All 6 models train and evaluate; best model selected automatically
**Status:** ✅ **COMPLETED** (2026-11-12)

#### TASK-038: SHAP Explainability [P1]
**Files:** `geneai/mutation_ml/explainability.py`
**Action:** Integrate SHAP for model interpretability
**Features:**
- TreeExplainer for tree-based models
- LinearExplainer for linear models
- PermutationExplainer fallback
- Single-variant explanation with top-k features
- Global feature importance (mean |SHAP|)
- Waterfall plots
- Force plots
- Summary plots (beeswarm)

**Acceptance:** Every prediction explainable with SHAP values
**Status:** ✅ **COMPLETED** (2026-11-12)

#### TASK-039: VCF Workflow Integration [P1]
**Files:** `geneai/mutation_ml/integration.py`
**Action:** Connect ML pipeline to existing VCF analyzer
**Features:**
- enhance_vcf_with_ml() - add ML predictions to VCF preview
- predict_single() - single variant prediction
- batch_predict() - multiple variants
- create_training_dataset_from_vcf() - labeled VCF → training data
- MLEnhancedVariant dataclass with all predictions + SHAP

**Acceptance:** VCF upload → ML-enhanced results with explanations
**Status:** ✅ **COMPLETED** (2026-11-12)

#### TASK-040: ML Dashboard [P2]
**Files:** `geneai/mutation_ml/dashboard.py`
**Action:** Streamlit dashboard for training, prediction, evaluation, explainability
**Tabs:**
- Model Training (VCF, CSV, Auto)
- Variant Prediction (Single, VCF batch, CSV batch)
- Model Evaluation (CV metrics, test metrics, ROC/PR curves, feature importance)
- Explainability (SHAP waterfall, force plots)
- Model Management (list, download, delete, upload)

**Acceptance:** Full ML lifecycle in UI
**Status:** ✅ **COMPLETED** (2026-11-12)

#### TASK-041: FastAPI REST API [P2]
**Files:** `geneai/mutation_ml/api.py`
**Action:** REST API endpoints for training, prediction, explanation
**Endpoints:**
- GET /health - Health check with model status
- GET /models - List saved models
- POST /models/load/{filename} - Load model
- POST /predict - Single variant prediction
- POST /predict/batch - Batch prediction
- POST /predict/vcf - VCF file prediction
- POST /explain - SHAP explanation
- POST /train - Train from VCF (placeholder)
- POST /train/matrix - Train from feature matrix
- DELETE /models/{filename} - Delete model
- GET /models/{filename}/download - Download model

**Acceptance:** API serves all ML functions
**Status:** ✅ **COMPLETED** (2026-11-12)

---

## Dependency Tracking

```
TASK-001 (Mock Tools) 
    → Blocks: TASK-011 (Tests), TASK-012 (Validation)

TASK-004 (Consolidate Code)
    → Blocks: TASK-006 (Migrations), TASK-007 (DB Leaks)

TASK-009 (Navigation) + TASK-010 (Global Theme)
    → Enables: TASK-019 (UI Template), TASK-023 (Dashboard)

TASK-013/014/015 (Phase 6 Modules)
    → Independent but share UI template (TASK-019)

TASK-016 (Lazy ML) + TASK-017 (Pooling) + TASK-018 (Parallel)
    → Independent performance improvements

TASK-024 (KG Viz) 
    → Requires: pyvis in requirements or Plotly replacement
```

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Breaking existing functionality during refactor | HIGH | HIGH | Comprehensive tests before each change; feature flags |
| ML model lazy loading causes first-request latency | MEDIUM | MEDIUM | Pre-warm on startup option; background loading |
| Navigation restructure confuses existing users | MEDIUM | LOW | Keep old URLs working; add redirect notices |
| Database migration fails in production | LOW | CRITICAL | Backup before migrate; test on staging; rollback plan |
| pyvis addition increases bundle size | LOW | LOW | Make optional; lazy load only on KG page |

---

## Success Criteria

### Week 1 Complete When:
- [ ] All mock tools replaced with real implementations
- [ ] No empty packages or broken imports
- [ ] REST API test console works with real endpoints
- [ ] Single rate limiter and exception hierarchy
- [ ] Health check endpoints respond correctly
- [ ] Database migrations work on test DB
- [ ] No DB connection leaks
- [ ] VCF limit safe for 8GB RAM
- [ ] Navigation categorized and searchable
- [ ] Professional UI applied globally

### Week 2 Complete When:
- [ ] Lab management, data management, QA modules functional
- [ ] ML models load lazily
- [ ] Connection pooling active
- [ ] Batch operations parallelized
- [ ] All tests passing

### Week 3-4 Complete When:
- [ ] All modules use standard UI template
- [ ] Sample data available everywhere
- [ ] Error handling consistent
- [ ] Help tooltips on all inputs
- [ ] Real dashboard with live metrics
- [ ] KG visualization works
- [ ] Charts theme-aware and exportable
- [ ] py3Dmol works offline

### Week 5-6 Complete When:
- [ ] Accessibility features integrated
- [ ] Documentation updated
- [ ] Integration tests cover key workflows
- [ ] Load testing validates 8GB RAM target
- [ ] Security audit passes

---

*End of Fixing Roadmap*