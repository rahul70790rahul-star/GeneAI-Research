# GeneAI Research - Bug and Error Report

**Generated:** 2026-11-12  
**Based on:** Complete code audit and static analysis

---

## Critical Bugs (Must Fix Immediately)

### BUG-001: Autonomous Agent Tools Return Mock Data
**Severity:** CRITICAL  
**Files:** `geneai/autonomous_agent/tools/*.py` (6 files)  
**Description:** All 6 tool categories (gene_analysis, protein_analysis, drug_analysis, disease_analysis, literature_analysis, workflow_tools) return hardcoded/fabricated results instead of calling real GeneAI modules.  
**Impact:** Violates scientific accuracy - produces fake research results.  
**Evidence:** Tools return static dictionaries with fabricated data (e.g., `{"gene": "TP53", "function": "tumor suppressor"}`).  
**Fix Required:** Replace mock implementations with actual calls to GeneAI modules (biotech_assistant tool_wrappers, multi_agent agents, etc.).
**Status:** ✅ **FIXED** - Replaced mock implementations in analysis_tools.py (Reactome, QuickGO, STRING, scipy), docking_tools.py (molecular_docking engine), and disease_tools.py (Open Targets API).

### BUG-002: Empty disease_intelligence Package
**Severity:** CRITICAL  
**Files:** `geneai/disease_intelligence/` (directory exists, no files)  
**Description:** Package directory exists with no `__init__.py` or modules, but is referenced in architecture documentation.  
**Impact:** Import errors if referenced; confusing for developers.  
**Fix Required:** Either implement the package or remove the directory and all references.
**Status:** ✅ **FIXED** - Removed empty directory; replaced functionality in autonomous_agent.tools.disease_tools using Open Targets API clients; updated geneai/__init__.py exports; updated tests.

### BUG-003: REST API Test Console Uses Mock Responses
**Severity:** HIGH  
**Files:** `geneai/rest_api/ui.py`  
**Description:** The API testing playground returns simulated responses instead of making actual API calls.  
**Impact:** Developers cannot test real endpoints; misleading during development.  
**Fix Required:** Connect test console to actual FastAPI endpoints via HTTP client.

### BUG-004: Duplicate DataSourceError Class Definition
**Severity:** HIGH  
**Files:** `geneai/drug_discovery/api_clients.py:51`, `geneai/drug_safety/data_integration.py`  
**Description:** `DataSourceError` exception class defined in two modules with potentially different behaviors.  
**Impact:** Inconsistent error handling; import conflicts possible.  
**Fix Required:** Move to shared location (e.g., `geneai/exceptions.py`) and import from there.

### BUG-005: Duplicate Rate Limiting Logic
**Severity:** HIGH  
**Files:** `geneai/drug_discovery/api_clients.py:60-69`, `geneai/drug_discovery/data_integration.py`, `geneai/drug_discovery/ncbi_client.py`  
**Description:** Rate limiting implementation duplicated across 3+ modules with different intervals.  
**Impact:** Inconsistent API throttling; maintenance burden; potential API bans.  
**Fix Required:** Create shared `RateLimiter` class in `geneai/utils/rate_limiter.py`.

---

## High Severity Bugs

### BUG-006: Variant Tools Mock Data (Referenced in Audit)
**Severity:** HIGH  
**Files:** `geneai/variant_tools.py` (referenced but not found in codebase)  
**Description:** Previous audit mentions `variant_tools.py` with hardcoded gnomAD AF=0.001, ClinVar VCV000123456, BRCA1 p.Ser123Arg.  
**Impact:** If this file exists elsewhere or is imported, it fabricates scientific results.  
**Fix Required:** Search for and remove/replace any variant annotation mocking.

### BUG-007: Missing Health Check Endpoint
**Severity:** HIGH  
**Files:** `app.py`, `geneai/rest_api/core.py`  
**Description:** No `/health` or `/ready` endpoint for Docker/Kubernetes liveness/readiness probes.  
**Impact:** Cannot deploy to production orchestration platforms.  
**Fix Required:** Add health check endpoint returning service status, DB connectivity, API connectivity.

### BUG-008: No Database Migration System
**Severity:** HIGH  
**Files:** All `database.py` modules  
**Description:** Schema changes require manual SQL; no version tracking or migration framework.  
**Impact:** Deployment failures; schema drift across environments.  
**Fix Required:** Implement Alembic or custom migration system with version table.

### BUG-009: Memory Leak Risk - Thread-Local DB Connections Not Closed
**Severity:** HIGH  
**Files:** All `database.py` modules (e.g., `geneai/unified_knowledge/database.py:444-448`)  
**Description:** Thread-local connections closed only on explicit `close()` call; Streamlit threads may persist.  
**Impact:** Connection leaks under load; SQLite lock contention.  
**Fix Required:** Add context managers; register cleanup via `atexit` or Streamlit session end.

### BUG-010: Large VCF Decompression Limit May Cause OOM
**Severity:** HIGH  
**Files:** `geneai/config.py:17`, `geneai/variants.py:139`, `geneai/mutation.py:205`  
**Description:** `MAX_VCF_DECOMPRESSED_BYTES = 2GB` - on 8GB RAM system, this can cause OOM with other processes.  
**Impact:** Application crash on large VCF files.  
**Fix Required:** Reduce default to 500MB; make configurable; add memory check before processing.

---

## Medium Severity Bugs

### BUG-011: Inconsistent Error Types Across Modules
**Severity:** MEDIUM  
**Files:** Throughout codebase  
**Description:** Mix of `ValueError`, `RuntimeError`, `DataSourceError`, custom exceptions without hierarchy.  
**Impact:** Difficult to catch specific errors; inconsistent user-facing messages.  
**Fix Required:** Define exception hierarchy in `geneai/exceptions.py`.

### BUG-012: No Input Validation on Some API Endpoints
**Severity:** MEDIUM  
**Files:** `geneai/rest_api/core.py`  
**Description:** Some FastAPI endpoints trust UI validation; direct API calls bypass checks.  
**Impact:** Potential injection, malformed requests cause 500 errors.  
**Fix Required:** Add Pydantic models for all request bodies; validate at endpoint level.

### BUG-013: Hardcoded Defaults Should Be Configurable
**Severity:** MEDIUM  
**Files:** Multiple modules  
**Description:** Values like `MAX_TARGETS=50`, `MAX_GENE_SYMBOLS=50`, timeouts hardcoded in modules.  
**Impact:** Cannot tune for different workloads without code changes.  
**Fix Required:** Move to `geneai/config.py` with environment variable overrides.

### BUG-014: Circular Import Risk in biotech_assistant/tool_wrappers.py
**Severity:** MEDIUM  
**Files:** `geneai/biotech_assistant/tool_wrappers.py` imports from 20+ modules  
**Description:** Tool wrappers import from modules that may import biotech_assistant.  
**Impact:** Potential import deadlocks; lazy imports mitigate but not eliminate.  
**Fix Required:** Use string-based dynamic imports; move tool registration to runtime.

### BUG-015: Py3Dmol Visualization May Fail Without Internet
**Severity:** MEDIUM  
**Files:** `geneai/drug_discovery/protein_ui.py`, `geneai/protein_intelligence/visualization.py`  
**Description:** 3D structure viewer loads py3Dmol from CDN; fails offline.  
**Impact:** Protein structure visualization broken in air-gapped environments.  
**Fix Required:** Bundle py3Dmol locally; add offline fallback.

### BUG-016: ML Model Loading Not Lazy
**Severity:** MEDIUM  
**Files:** `geneai/admet_prediction/ml_models.py`, `geneai/drug_target_prediction/ml_models.py`, `geneai/drug_safety/ml_models.py`  
**Description:** XGBoost/LightGBM/PyTorch models loaded at module import.  
**Impact:** High memory usage at startup (~500MB+); slow app initialization.  
**Fix Required:** Implement lazy loading with `@cached` decorator; load on first prediction.

### BUG-017: Batch Comparison in ADMET UI Blocks UI Thread
**Severity:** MEDIUM  
**Files:** `geneai/admet_prediction/admet_ui.py:246-280`  
**Description:** `render_batch_comparison()` runs predictions sequentially with `st.progress` blocking Streamlit.  
**Impact:** UI freezes during batch processing; no cancellation.  
**Fix Required:** Use `background_process` or thread pool; add cancel button.

### BUG-018: Knowledge Graph Visualization Requires pyvis (Not in Requirements)
**Severity:** MEDIUM  
**Files:** `geneai/ai_research_intelligence/knowledge_graph.py`  
**Description:** Graph visualization code references `pyvis` but it's not in requirements.txt.  
**Impact:** ImportError if visualization attempted.  
**Fix Required:** Add `pyvis` to requirements or make visualization optional with try/except.

### BUG-019: Multi-User Auth Uses In-Memory Session Store
**Severity:** MEDIUM  
**Files:** `geneai/multi_user/core.py`  
**Description:** Sessions stored in memory; lost on restart; no distributed session support.  
**Impact:** Users logged out on deploy; doesn't scale to multiple workers.  
**Fix Required:** Use Redis-backed sessions; add session persistence.

### BUG-020: Cloud Integration LocalStorage Not Thread-Safe
**Severity:** MEDIUM  
**Files:** `geneai/cloud_integration/core.py`  
**Description:** `LocalStorage` uses filesystem operations without locking.  
**Impact:** Race conditions on concurrent uploads/downloads.  
**Fix Required:** Add file locking; use thread-safe operations.

---

## Low Severity / Code Quality Issues

### BUG-021: Unused Import in molecular_docking/docking_ui.py
**Severity:** LOW  
**Files:** `geneai/molecular_docking/docking_ui.py:12`  
**Description:** `from rdkit.Chem import AllChem` imported but `AllChem` used without prefix.  
**Fix:** Use `AllChem.EmbedMolecule` or change import.

### BUG-022: Missing Type Hints in Several Modules
**Severity:** LOW  
**Files:** Multiple  
**Description:** Some functions lack return type annotations.  
**Fix:** Add type hints for better IDE support and mypy checking.

### BUG-023: Inconsistent Logging Levels
**Severity:** LOW  
**Files:** Throughout  
**Description:** Mix of `logger.info`, `logger.warning`, `logger.error` without standard.  
**Fix:** Define logging standards; use structured logging.

### BUG-024: TODO/FIXME Comments in Code
**Severity:** LOW  
**Files:** Multiple  
**Description:** Several TODO comments indicating incomplete features.  
**Fix:** Convert to GitHub issues; implement or remove.

### BUG-025: Test Files Reference Non-Existent Fixtures
**Severity:** LOW  
**Files:** `tests/conftest.py` (if exists)  
**Description:** Some tests may reference missing fixture files.  
**Fix:** Verify all test fixtures exist; create synthetic data generators.

---

## Dependency Issues

### DEP-001: Missing openpyxl for Excel Import
**Severity:** MEDIUM  
**Required For:** Phase 6 Data Management (not yet implemented)  
**Fix:** Add `openpyxl>=3.1,<4.0` to requirements.txt

### DEP-002: Missing pyvis for Knowledge Graph Visualization
**Severity:** MEDIUM  
**Required For:** `geneai/ai_research_intelligence/knowledge_graph.py` visualization  
**Fix:** Add `pyvis>=0.3,<1.0` to requirements.txt or make optional

### DEP-003: Optional Dependencies Not Declared
**Severity:** LOW  
**Modules:** `ml_explainability` (shap), `ml_optimization` (optuna), `deep_learning` (torch, torch-geometric), `ml_registry` (mlflow)  
**Issue:** These are in requirements.txt but should be optional with graceful degradation.  
**Fix:** Keep in requirements but ensure try/except imports work (already done in __init__.py files).

---

## UI/UX Bugs

### UI-001: Navigation Sidebar Has 89 Uncategorized Items
**Severity:** HIGH (Usability)  
**Files:** `app.py:51-92`  
**Description:** Flat radio list of 89 pages; no grouping, search, or favorites.  
**Impact:** Users cannot find modules; overwhelming.  
**Fix Required:** Redesign with categorized navigation (see UI_UX_AUDIT.md).

### UI-002: Professional UI Components Not Applied Globally
**Severity:** MEDIUM  
**Files:** `geneai/professional_ui/core.py` vs individual module UIs  
**Description:** Professional theming only active on "Professional UI" page; other pages use default Streamlit.  
**Impact:** Inconsistent visual experience.  
**Fix Required:** Call `inject_professional_css()` in `app.py` before rendering pages.

### UI-003: No Loading States for Long Operations
**Severity:** MEDIUM  
**Files:** Multiple UI modules  
**Description:** Some operations show `st.spinner` but no progress for multi-step operations.  
**Impact:** User uncertainty during long computations.  
**Fix Required:** Add progress bars with step descriptions; use `st.status` (Streamlit 1.27+).

### UI-004: Empty States Not Handled Consistently
**Severity:** LOW  
**Files:** Multiple UI modules  
**Description:** Some pages show "No data" captions; others show empty tables; professional_ui has `pro_empty_state` but unused.  
**Fix Required:** Standardize on `pro_empty_state` component.

### UI-005: No Keyboard Shortcuts or Accessibility Features
**Severity:** LOW  
**Files:** `geneai/professional_ui/core.py` has `announce_to_screen_reader` but unused  
**Description:** Accessibility helpers exist but not integrated into main app.  
**Fix Required:** Add screen reader announcements for dynamic content; keyboard navigation.

---

## Security Vulnerabilities

### SEC-001: API Keys in Environment Variables Only
**Severity:** MEDIUM  
**Files:** `.env.example`, `geneai/config.py`  
**Description:** No secret rotation, encryption at rest, or access auditing for API keys.  
**Fix:** Integrate with HashiCorp Vault or AWS Secrets Manager for production.

### SEC-002: No Rate Limiting on Streamlit UI Endpoints
**Severity:** LOW  
**Files:** `app.py`  
**Description:** Streamlit has no built-in rate limiting; authenticated users can DoS via heavy computations.  
**Fix:** Add per-user rate limiting for expensive operations (docking, batch screening).

### SEC-003: File Upload No Content Validation
**Severity:** LOW  
**Files:** `app.py`, various UI modules  
**Description:** File uploads validated by extension only; no MIME type or content verification.  
**Fix:** Add python-magic content validation; sanitize filenames.

---

## Performance Issues

### PERF-001: All Databases Open Connections Per Session
**Severity:** MEDIUM  
**Impact:** On 8GB RAM, 11 databases × thread-local connections = memory pressure.  
**Fix:** Implement connection pooling; close idle connections.

### PERF-002: No Query Result Caching for Repeated Searches
**Severity:** MEDIUM  
**Impact:** Same disease/gene searches hit external APIs repeatedly despite TTL cache.  
**Fix:** Ensure all API clients use `@ttl_cache`; add cache statistics to UI.

### PERF-003: Molecular Docking Runs Sequentially in Batch Mode
**Severity:** MEDIUM  
**Files:** `geneai/molecular_docking/docking_ui.py:1095-1110`  
**Impact:** Batch docking of 80+ ligands takes hours sequentially.  
**Fix:** Add multiprocessing/thread pool for parallel docking.

### PERF-004: Knowledge Graph Centrality Computation Not Cached
**Severity:** LOW  
**Files:** `geneai/ai_research_intelligence/knowledge_graph.py`  
**Impact:** Recomputes on every request.  
**Fix:** Add `@ttl_cache` to `compute_centrality`.

---

## Summary by Category

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Functional Bugs | 2 | 4 | 10 | 5 | 21 |
| Dependency Issues | 0 | 0 | 2 | 1 | 3 |
| UI/UX Bugs | 0 | 1 | 2 | 2 | 5 |
| Security | 0 | 0 | 1 | 2 | 3 |
| Performance | 0 | 0 | 4 | 0 | 4 |
| **Total** | **2** | **5** | **19** | **10** | **36** |

---

## Fix Priority Order

1. **BUG-001** - Autonomous agent mock tools (CRITICAL - scientific integrity)
2. **BUG-002** - Empty disease_intelligence package (CRITICAL - broken imports)
3. **BUG-003** - REST API mock console (HIGH - developer experience)
4. **BUG-004/005** - Duplicate code consolidation (HIGH - maintainability)
5. **BUG-007** - Health check endpoint (HIGH - production deployment)
6. **BUG-008** - Database migrations (HIGH - deployment reliability)
7. **BUG-009** - DB connection leaks (HIGH - stability)
8. **BUG-010** - VCF memory limit (HIGH - crash prevention)
9. **UI-001** - Navigation redesign (HIGH - usability)
10. **BUG-016** - Lazy ML model loading (MEDIUM - startup performance)
... and so on

---

*End of Bug and Error Report*