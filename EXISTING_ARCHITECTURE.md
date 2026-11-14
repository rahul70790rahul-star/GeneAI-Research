# GeneAI Research - Existing Architecture Documentation

**Generated:** 2026-11-11  
**Based on:** PROJECT_INSPECTION.md analysis  
**Purpose:** Technical architecture reference for Phase 6 development

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        STREAMLIT FRONTEND (app.py)                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────┐  │
│  │ 38+ Pages    │ │  Session     │ │  Component   │ │  Theme    │  │
│  │  Navigation  │ │  State       │ │  Library     │ │  Engine   │  │
│  └──────────────┘ └──────────────┘ └──────────────┘ └───────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      GENEAI PACKAGE (geneai/)                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  __init__.py - Central API exports (600+ symbols)            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ Core     │ │ Drug     │ │ AI/ML    │ │ Platform │ │ Phase 6│  │
│  │ Utils    │ │ Discovery│ │ Pipeline │ │ Services │ │ Agent  │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
            ┌────────────┐ ┌────────────┐ ┌────────────┐
            │  SQLite    │ │  External  │ │  File      │
            │  (WAL)     │ │  APIs      │ │  Storage   │
            └────────────┘ └────────────┘ └────────────┘
```

---

## 2. Core Design Patterns

### 2.1 Module Organization
Each feature domain follows a consistent structure:
```
geneai/<module_name>/
├── __init__.py          # Public API exports
├── core.py              # Business logic (or <module>_engine.py)
├── database.py          # SQLite persistence (if needed)
├── *_ui.py              # Streamlit UI components
├── api_clients.py       # External API wrappers (if needed)
├── report_generator.py  # Report generation (if needed)
└── <specialized>.py     # Domain-specific modules
```

### 2.2 Database Access Pattern
- **Thread-local connections** via `get_db()` in each module's `database.py`
- **WAL mode** enabled for concurrent access
- **Parameterized queries** only - no raw SQL interpolation
- **JSON serialization** for complex objects (lists, dicts)
- **Per-module schemas** with isolated table prefixes

```python
# Typical pattern in geneai/<module>/database.py
import sqlite3
import threading
from contextlib import contextmanager

_thread_local = threading.local()

def get_db() -> sqlite3.Connection:
    if not hasattr(_thread_local, 'conn'):
        _thread_local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _thread_local.conn.execute("PRAGMA journal_mode=WAL")
        _thread_local.conn.row_factory = sqlite3.Row
    return _thread_local.conn

@contextmanager
def transaction():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

### 2.3 External API Client Pattern
- **Retry logic** with exponential backoff
- **Rate limiting** via `croniter` + `flask-limiter`
- **Caching** with TTL (in-memory or SQLite)
- **Error handling** with specific exception types
- **Response validation** against expected schemas

```python
# Typical pattern in geneai/<module>/api_clients.py
import requests
from functools import lru_cache
from tenacity import retry, stop_after_attempt, wait_exponential

class SomeAPIClient:
    BASE_URL = "https://api.example.org"
    RATE_LIMIT = 10  # requests/second
    
    @retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
    def fetch(self, endpoint: str, params: dict) -> dict:
        response = requests.get(f"{self.BASE_URL}/{endpoint}", params=params, timeout=30)
        response.raise_for_status()
        return response.json()
```

### 2.4 Streamlit UI Pattern
- **Page functions** named `render_<feature>_dashboard()` or `render_<feature>_ui()`
- **Session state** for persistence across reruns
- **Forms** for user input with validation
- **Containers/borders** for visual grouping
- **Download buttons** for data export (CSV, JSON, Markdown)
- **Expanders** for progressive disclosure

```python
# Typical pattern in geneai/<module>/*_ui.py
import streamlit as st

def render_feature_dashboard():
    st.header("Feature Dashboard")
    
    with st.form("input_form"):
        # Input widgets
        submitted = st.form_submit_button("Run Analysis")
    
    if submitted:
        with st.spinner("Processing..."):
            results = run_analysis(params)
        
        # Display results
        st.dataframe(results)
        st.download_button("Export", results.to_csv(), "results.csv")
```

---

## 3. Data Flow Architecture

### 3.1 Request Flow (Streamlit → Processing → Response)
```
User Action (UI)
      │
      ▼
Streamlit Event Handler (app.py page logic)
      │
      ▼
GeneAI Module Function (e.g., run_disease_analysis())
      │
      ├──▶ SQLite Database (read/write)
      │
      ├──▶ External API Clients (NCBI, UniProt, etc.)
      │       │
      │       ├──▶ Request with retry/backoff
      │       ├──▶ Response validation
      │       └──▶ Cache update
      │
      ├──▶ ML Models (XGBoost, LightGBM, PyTorch, SHAP, Optuna)
      │
      └──▶ Report Generation (PDF, CSV, JSON, Markdown)
            │
            ▼
      Streamlit Response (dataframe, charts, downloads)
```

### 3.2 Autonomous Agent Flow (Phase 6.1)
```
Research Question (Natural Language)
      │
      ▼
AutonomousBioAgent.process_question()
      │
      ├──▶ TaskPlanner.decompose() → TaskPlan (DAG of tasks)
      │       │
      │       ├──▶ Template matching (mutation→drug, target ID, etc.)
      │       └──▶ Parameter extraction from question
      │
      ├──▶ ApprovalManager.request_approval() (for sensitive tools)
      │
      ├──▶ ToolOrchestrator.execute_plan() (concurrent, dependency-aware)
      │       │
      │       ├──▶ ToolRegistry.get(tool_name)
      │       ├──▶ ErrorRecovery (retry with backoff)
      │       ├──▶ WorkflowMonitor.record_*()
      │       └──▶ TaskResult collection
      │
      ├──▶ ExecutionHistory.record_*() (audit trail)
      │
      ├──▶ AgentMemory.add_entry() (conversation context)
      │
      └──▶ Summary Generation → ResearchResult
```

---

## 4. Key Technical Decisions

### 4.1 SQLite with WAL Mode
**Rationale:** 
- Zero-configuration, file-based
- WAL enables concurrent readers + single writer
- Sufficient for research workloads (< 100 concurrent users)
- Portable across environments

**Trade-offs:**
- Not suitable for high-write production
- No built-in replication
- Migration to PostgreSQL planned for cloud deployment

### 4.2 Thread-Local Connections
**Rationale:**
- Streamlit runs each session in separate thread
- Avoids connection sharing issues
- Simple implementation

**Trade-offs:**
- Connection pooling not used
- Connection count = active sessions

### 4.3 JSON Serialization for Complex Types
**Rationale:**
- Schema flexibility for evolving data
- Avoids ALTER TABLE migrations
- Native SQLite JSON1 extension support

**Trade-offs:**
- No SQL querying inside JSON
- Larger storage size
- Type safety at application layer only

### 4.3 Lazy Imports for Optional Dependencies
**Pattern:** Used in `ml_explainability`, `ml_optimization`, `deep_learning`, `ml_registry`
```python
# geneai/ml_explainability/__init__.py
try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    shap = None
```
**Rationale:** Allows base installation without heavy ML dependencies

### 4.4 Central Configuration (`geneai/config.py`)
- Environment variable overrides
- API key management
- Database path configuration
- Default parameters for all modules

---

## 5. Module Dependency Graph

### 5.1 Core Dependencies (No internal deps)
```
sequence.py, variants.py, mutation.py, report.py, research.py, lab.py, config.py
```

### 5.2 Domain Modules (Depend on core + external APIs)
```
admet_prediction/     → sequence.py, variants.py, config.py
biomarker_discovery/  → sequence.py, variants.py, config.py
disease_gene_pathway/ → sequence.py, variants.py, config.py
drug_discovery/       → sequence.py, variants.py, config.py + all API clients
drug_repurposing/     → drug_discovery/, config.py
drug_safety/          → admet_prediction/, config.py
drug_target_prediction/ → drug_discovery/, config.py
integrated_precision/ → drug_discovery/, admet_prediction/, disease_gene_pathway/, biomarker_discovery/, drug_safety/, drug_target_prediction/
```

### 5.3 Platform Modules (Cross-cutting)
```
biotech_assistant/     → All domain modules (via tool_wrappers)
multi_agent/           → All domain modules (via agents)
unified_knowledge/     → All domain modules (via loaders)
research_automation/   → All domain modules (via step executors)
ai_research_intelligence/ → drug_discovery/, admet_prediction/, disease_gene_pathway/, biomarker_discovery/, drug_safety/, drug_target_prediction/
ml_explainability/     → All ML modules
ml_optimization/       → All ML modules
deep_learning/         → Standalone (PyTorch)
ml_registry/           → All ML modules
multi_user/            → Standalone (auth)
cloud_integration/     → Standalone (cloud SDKs)
rest_api/              → All modules (via API endpoints)
security/              → All modules (via audit/encryption)
performance/           → All modules (via caching/monitoring)
professional_ui/       → All modules (via theming)
autonomous_agent/      → All modules (via tool registry)  ← NEW Phase 6.1
```

### 5.4 Circular Dependency Risks
**Identified:**
- `biotech_assistant` ↔ domain modules (via tool_wrappers)
- `multi_agent` ↔ domain modules (via agents)
- `integrated_precision` ↔ multiple domain modules
- `autonomous_agent` ↔ all modules (via tools)

**Mitigation:**
- Lazy imports in `__init__.py`
- Tool wrappers use string-based module paths
- Central `geneai/__init__.py` exports only, no logic

---

## 6. Security Architecture

### 6.1 Encryption (`geneai/security/core.py`)
- **DataEncryption**: AES-256-GCM for field-level encryption
- **FieldEncryption**: Transparent model field encryption
- **SecureStorage**: Encrypted key-value store
- **EncryptionKey**: Key rotation and derivation (PBKDF2)

### 6.2 Audit Logging
- **AuditLogger**: Structured event logging to SQLite
- **AuditEventType**: 15+ event types (data_access, auth, config_change, etc.)
- **SecurityLevel**: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED

### 6.3 Access Control
- **AccessControl**: RBAC with resource-level permissions
- **SessionSecurity**: Token management, CSRF protection
- **DataPrivacy**: GDPR-compliant data handling

### 6.4 Multi-User (`geneai/multi_user/core.py`)
- **AuthManager**: JWT-based authentication
- **User/Team/Project**: Hierarchical organization
- **Roles**: USER, ADMIN, OWNER with granular permissions

---

## 7. Performance Architecture

### 7.1 Caching (`geneai/performance/core.py`)
- **LRUCache**: Thread-safe in-memory cache
- **MultiLevelCache**: L1 (memory) + L2 (SQLite) + L3 (Redis-ready)
- **AsyncCache**: Async-compatible cache wrapper
- **@cached decorator**: Function-level caching with TTL

### 7.2 Monitoring
- **PerformanceMonitor**: Request/operation timing
- **PerformanceMetrics**: Latency, throughput, error rates
- **QueryOptimizer**: SQL query analysis and indexing hints
- **ResourcePool**: Connection/thread pool management
- **BatchProcessor**: Batched operations for throughput

### 7.3 Optimization Strategies
- **Lazy loading** for heavy ML models
- **Streaming VCF parsing** for large files (>50MB)
- **Pagination** for large result sets
- **Background jobs** for long-running operations

---

## 8. ML/AI Pipeline Architecture

### 8.1 Training Pipeline
```
Raw Data → Data Integration → Feature Engineering → Model Training → Evaluation → Registry
    │              │                  │                  │              │            │
    ▼              ▼                  ▼                  ▼              ▼            ▼
SQLite/CSV    geneai/<module>/    geneai/<module>/   XGBoost/        Metrics      MLflow
              data_integration    ml_models          LightGBM/       (AUC, F1)   Tracking
                                                           PyTorch
```

### 8.2 Inference Pipeline
```
Input → Preprocessing → Model Load → Prediction → Post-processing → Explainability → Response
  │           │              │            │              │                │           │
  ▼           ▼              ▼            ▼              ▼                ▼           ▼
API/UI   geneai/<module>/  MLflow       XGBoost/       Threshold/      SHAP        JSON/
       molecular_props    Model        LightGBM/      Calibration     Values      DataFrame
                          Registry     PyTorch
```

### 8.3 ML Modules Integration Points
| Module | Role | Consumers |
|--------|------|-----------|
| `ml_explainability` | SHAP explanations | ADMET, Safety, Ranking, Target |
| `ml_optimization` | Hyperparameter tuning | All ML models |
| `deep_learning` | GNN/MLP for molecules | ADMET, Drug design |
| `ml_registry` | MLflow tracking/registry | All ML modules |

---

## 9. Deployment Architecture

### 9.1 Local Development
```
Streamlit (port 8501) → geneai package → SQLite (file) → External APIs
```

### 9.2 Production (Planned)
```
                    ┌─────────────┐
                    │  Nginx      │  (SSL, rate limit, static)
                    │  (port 80/443)│
                    └──────┬──────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
       ┌─────────┐   ┌─────────┐    ┌─────────┐
       │Streamlit│   │Streamlit│    │Streamlit│  (Multiple workers)
       │Worker 1 │   │Worker 2 │    │Worker N │
       └────┬────┘   └────┬────┘    └────┬────┘
            │             │             │
            └─────────────┼─────────────┘
                          ▼
                   ┌─────────────┐
                   │  PostgreSQL │  (Primary DB)
                   │  (Patroni)  │
                   └──────┬──────┘
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
       ┌─────────┐  ┌──────────┐  ┌──────────┐
       │ Redis   │  │  MinIO   │  │  MLflow  │
       │ (Cache) │  │ (Artifacts)│ │ (Models) │
       └─────────┘  └──────────┘  └──────────┘
```

### 9.3 Docker/Kubernetes (nginx/ directory exists)
- Multi-stage Dockerfile
- Health checks
- Horizontal pod autoscaling
- Persistent volumes for PostgreSQL/MinIO

---

## 10. Testing Architecture

### 10.1 Test Structure
```
tests/
├── test_smoke.py              # Import verification
├── test_ml_enhancements.py    # Phase 5.13 ML tests
├── conftest.py                # Pytest fixtures (if exists)
└── <module>_test.py           # Per-module tests (planned)
```

### 10.2 Test Categories
| Category | Scope | Tools |
|----------|-------|-------|
| Smoke | Import all modules | pytest |
| Unit | Individual functions | pytest + pytest-mock |
| Integration | Module workflows | pytest + test DB |
| API | REST endpoints | pytest + httpx |
| UI | Streamlit pages | playwright (planned) |

### 10.3 Test Data
- Synthetic test data in `tests/fixtures/`
- Mocked external APIs via `pytest-mock`
- Temporary SQLite databases per test

---

## 11. Configuration Management

### 11.1 Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `GENEAI_DATABASE_PATH` | SQLite database location | `./geneai.db` |
| `NCBI_API_KEY` | NCBI E-utilities key | None |
| `UNIPROT_API_KEY` | UniProt access | None |
| `CHEMBL_API_KEY` | ChEMBL access | None |
| `OPENTARGETS_API_KEY` | OpenTargets access | None |
| `MLFLOW_TRACKING_URI` | MLflow server | `sqlite:///mlflow.db` |
| `REDIS_URL` | Cache backend | None |
| `SECRET_KEY` | JWT/encryption | Generated |
| `LOG_LEVEL` | Logging verbosity | INFO |

### 11.2 Configuration Precedence
1. Environment variables (highest)
2. `geneai/config.py` defaults
3. Module-level constants

---

## 12. Extension Points for Phase 6

### 12.1 Autonomous Agent Tools
New tools register via `ToolRegistry` in `autonomous_agent/tools/__init__.py`:
```python
from geneai.autonomous_agent.tools import get_tool_registry, Tool, ToolSpec, ToolParameter

class MyNewTool(Tool):
    def __init__(self):
        super().__init__(ToolSpec(
            name="my_tool",
            description="...",
            category="analysis",
            parameters=[ToolParameter(...)]
        ))
    
    def execute(self, **kwargs) -> dict:
        # Implementation
        return {"result": "..."}

# Register
get_tool_registry().register(MyNewTool())
```

### 12.2 Multi-Agent Specialized Agents
Add new agents in `multi_agent/agents.py`:
```python
class GenomicsAgent(BaseAgent):
    CAPABILITIES = [AgentCapability.GENE_ANALYSIS, AgentCapability.VARIANT_ANALYSIS]
    
    async def process(self, message: AgentMessage) -> AgentMessage:
        # Implementation
        return AgentMessage(...)

# Register in create_all_agents()
```

### 12.3 Unified Knowledge Loaders
Add loaders in `unified_knowledge/loaders.py`:
```python
class NewDataLoader(BaseLoader):
    SOURCE_NAME = "new_source"
    
    def load(self, db: KnowledgeDatabase, config: DatabaseConfig) -> LoadStats:
        # Implementation
        return LoadStats(...)

# Register in load_all_data()
```

---

## 13. Known Technical Debt

1. **No API versioning** - REST API uses single version
2. **SQLite connection limits** - Thread-local, no pooling
3. **Missing input validation** - Some endpoints trust UI validation
4. **Inconsistent error types** - Mix of ValueError, RuntimeError, custom
5. **No structured logging** - Uses stdlib logging, no JSON format
6. **Limited test coverage** - Only smoke tests exist
7. **No database migrations** - Schema changes require manual SQL
8. **Hardcoded defaults** - Some module constants should be configurable
9. **Circular import risk** - Mitigated but not eliminated
10. **No observability** - No distributed tracing, metrics export

---

## 14. Architecture Decision Records (ADRs)

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| 001 | SQLite with WAL for local deployment | Accepted | Phase 1 |
| 002 | Thread-local DB connections | Accepted | Phase 1 |
| 003 | JSON serialization for complex types | Accepted | Phase 2 |
| 004 | Lazy imports for optional ML deps | Accepted | Phase 5.13 |
| 005 | Shared types module for circular import fix | Accepted | Phase 6.1 |
| 006 | Tool registry pattern for autonomous agent | Accepted | Phase 6.1 |
| 007 | Task DAG with dependency resolution | Accepted | Phase 6.1 |

---

*This document should be updated with each Phase 6 module implementation.*