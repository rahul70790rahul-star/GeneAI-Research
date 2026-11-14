"""Laboratory Management System - Phase 6."""
from __future__ import annotations
import logging, sqlite3, uuid, json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any
from geneai.config import DATABASE_PATH
logger = logging.getLogger(__name__)
DB_PATH = DATABASE_PATH
SAMPLE_STATUSES = {"received","in_storage","processing","analyzed","archived","discarded"}
EXPERIMENT_STATUSES = {"planned","in_progress","completed","paused","cancelled","failed"}
RESULT_STATUSES = {"pending","verified","flagged","rejected"}
MATERIALS = {"DNA","RNA","Protein","Cell","Tissue","Compound","Other"}

@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        _create_tables(conn)
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback(); logger.exception("SQLite error in lab_management"); raise
    finally:
        conn.close()

def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS samples (
        sample_id TEXT PRIMARY KEY, name TEXT NOT NULL, material TEXT NOT NULL,
        project TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'received', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS experiments (
        experiment_id TEXT PRIMARY KEY, name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', project_id TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'planned', created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL, completed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS experiment_samples (
        experiment_id TEXT NOT NULL, sample_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'input', added_at TEXT NOT NULL,
        PRIMARY KEY (experiment_id, sample_id)
    );
    CREATE TABLE IF NOT EXISTS projects (
        project_id TEXT PRIMARY KEY, name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS datasets (
        dataset_id TEXT PRIMARY KEY, name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '', project_id TEXT NOT NULL DEFAULT '',
        file_path TEXT NOT NULL DEFAULT '', file_type TEXT NOT NULL DEFAULT '',
        row_count INTEGER NOT NULL DEFAULT 0, column_count INTEGER NOT NULL DEFAULT 0,
        validation_status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS results (
        result_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL,
        name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        result_type TEXT NOT NULL DEFAULT 'observation', data_json TEXT NOT NULL DEFAULT '{}',
        status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sample_status_history (
        history_id TEXT PRIMARY KEY, sample_id TEXT NOT NULL,
        previous_status TEXT NOT NULL DEFAULT '', new_status TEXT NOT NULL,
        changed_at TEXT NOT NULL, changed_by TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS lab_schema_version (
        version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
    );
    """)
    row = conn.execute("SELECT version FROM lab_schema_version ORDER BY version DESC LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO lab_schema_version (version, applied_at) VALUES (1, ?)",
                     (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
    _migrate_samples_table(conn)

def _migrate_samples_table(conn: sqlite3.Connection) -> None:
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(samples)")}
    if "status" not in columns:
        conn.execute("ALTER TABLE samples ADD COLUMN status TEXT NOT NULL DEFAULT 'received'")
    if "updated_at" not in columns:
        conn.execute("ALTER TABLE samples ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute("UPDATE samples SET updated_at = ? WHERE updated_at = '' OR updated_at IS NULL", (now,))
def add_sample(name, material, project="", notes="", status="received") -> str:
    """Register a sample and return its unique identifier."""
    name = name.strip()
    if not name: raise ValueError("Sample name is required.")
    material = material.strip()
    if material not in MATERIALS: raise ValueError("Choose a supported sample material.")
    status = status.strip().lower()
    if status not in SAMPLE_STATUSES: raise ValueError(f"Invalid status: {status}")
    sample_id = "GAR-" + uuid.uuid4().hex[:10].upper()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as db:
        db.execute("""INSERT INTO samples
            (sample_id,name,material,project,notes,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (sample_id, name, material, project.strip(), notes.strip(), status, now, now))
    logger.info("Registered sample %s", sample_id)
    return sample_id

def load_samples() -> list[dict[str, str]]:
    """Return all samples newest first."""
    with _connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM samples ORDER BY created_at DESC")]

def get_sample(sample_id: str) -> dict[str, str] | None:
    """Return a single sample by ID, or None if not found."""
    with _connect() as db:
        r = db.execute("SELECT * FROM samples WHERE sample_id = ?", (sample_id,)).fetchone()
        return dict(r) if r else None

def update_sample(sample_id: str, *, name=None, material=None, project=None, notes=None, status=None) -> bool:
    """Update fields of an existing sample. Returns True if updated."""
    with _connect() as db:
        r = db.execute("SELECT * FROM samples WHERE sample_id = ?", (sample_id,)).fetchone()
        if r is None: return False
        updates, params = [], []
        if name is not None:
            name = name.strip()
            if not name: raise ValueError("Sample name cannot be empty.")
            updates.append("name = ?"); params.append(name)
        if material is not None:
            if material not in MATERIALS: raise ValueError("Unsupported sample material.")
            updates.append("material = ?"); params.append(material)
        if project is not None: updates.append("project = ?"); params.append(project.strip())
        if notes is not None: updates.append("notes = ?"); params.append(notes.strip())
        if status is not None:
            status = status.strip().lower()
            if status not in SAMPLE_STATUSES: raise ValueError(f"Invalid status: {status}")
            updates.append("status = ?"); params.append(status)
        if not updates: return False
        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat(timespec="seconds"))
        params.append(sample_id)
        db.execute(f"UPDATE samples SET {', '.join(updates)} WHERE sample_id = ?", params)
        return True

def delete_sample(sample_id: str) -> bool:
    """Delete a sample and its associations. Returns True if deleted."""
    with _connect() as db:
        r = db.execute("SELECT * FROM samples WHERE sample_id = ?", (sample_id,)).fetchone()
        if r is None: return False
        db.execute("DELETE FROM experiment_samples WHERE sample_id = ?", (sample_id,))
        db.execute("DELETE FROM sample_status_history WHERE sample_id = ?", (sample_id,))
        db.execute("DELETE FROM samples WHERE sample_id = ?", (sample_id,))
        return True

def set_sample_status(sample_id: str, new_status: str, changed_by: str = "", reason: str = "") -> bool:
    """Transition a sample to a new status and record the change in history."""
    new_status = new_status.strip().lower()
    if new_status not in SAMPLE_STATUSES: raise ValueError(f"Invalid status: {new_status}")
    with _connect() as db:
        r = db.execute("SELECT * FROM samples WHERE sample_id = ?", (sample_id,)).fetchone()
        if r is None: return False
        prev = r["status"]; now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.execute("UPDATE samples SET status = ?, updated_at = ? WHERE sample_id = ?", (new_status, now, sample_id))
        db.execute("""INSERT INTO sample_status_history
            (history_id,sample_id,previous_status,new_status,changed_at,changed_by,reason)
            VALUES (?,?,?,?,?,?,?)""",
            ("HIS-" + uuid.uuid4().hex[:10].upper(), sample_id, prev, new_status, now, changed_by, reason))
        return True

def get_sample_status_history(sample_id: str) -> list[dict[str, str]]:
    """Return the status change history for a sample."""
    with _connect() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM sample_status_history WHERE sample_id = ? ORDER BY changed_at DESC", (sample_id,))]
def create_experiment(name: str, description: str = "", project_id: str = "") -> str:
    """Create a new experiment and return its ID."""
    name = name.strip()
    if not name: raise ValueError("Experiment name is required.")
    eid = "EXP-" + uuid.uuid4().hex[:10].upper()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as db:
        db.execute("""INSERT INTO experiments
            (experiment_id,name,description,project_id,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)""", (eid, name, description, project_id.strip(), "planned", now, now))
    return eid

def load_experiments() -> list[dict[str, str]]:
    """Return all experiments newest first."""
    with _connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM experiments ORDER BY created_at DESC")]

def get_experiment(experiment_id: str) -> dict[str, str] | None:
    """Return a single experiment by ID, or None if not found."""
    with _connect() as db:
        r = db.execute("SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
        return dict(r) if r else None

def update_experiment(experiment_id: str, *, name=None, description=None, project_id=None, status=None) -> bool:
    """Update fields of an existing experiment. Returns True if updated."""
    with _connect() as db:
        r = db.execute("SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
        if r is None: return False
        updates, params = [], []
        if name is not None:
            name = name.strip()
            if not name: raise ValueError("Experiment name cannot be empty.")
            updates.append("name = ?"); params.append(name)
        if description is not None: updates.append("description = ?"); params.append(description)
        if project_id is not None: updates.append("project_id = ?"); params.append(project_id.strip())
        if status is not None:
            status = status.strip().lower()
            if status not in EXPERIMENT_STATUSES: raise ValueError(f"Invalid status: {status}")
            updates.append("status = ?"); params.append(status)
            if status == "completed" and r["completed_at"] is None:
                updates.append("completed_at = ?"); params.append(datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if not updates: return False
        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat(timespec="seconds"))
        params.append(experiment_id)
        db.execute(f"UPDATE experiments SET {', '.join(updates)} WHERE experiment_id = ?", params)
        return True

def delete_experiment(experiment_id: str) -> bool:
    """Delete an experiment and its sample associations. Returns True if deleted."""
    with _connect() as db:
        r = db.execute("SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone()
        if r is None: return False
        db.execute("DELETE FROM experiment_samples WHERE experiment_id = ?", (experiment_id,))
        db.execute("DELETE FROM results WHERE experiment_id = ?", (experiment_id,))
        db.execute("DELETE FROM experiments WHERE experiment_id = ?", (experiment_id,))
        return True

def add_sample_to_experiment(experiment_id: str, sample_id: str, role: str = "input") -> bool:
    """Associate a sample with an experiment. Returns True if added."""
    with _connect() as db:
        if not db.execute("SELECT 1 FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone(): return False
        if not db.execute("SELECT 1 FROM samples WHERE sample_id = ?", (sample_id,)).fetchone(): return False
        try:
            db.execute("""INSERT INTO experiment_samples (experiment_id,sample_id,role,added_at)
                VALUES (?,?,?,?)""", (experiment_id, sample_id, role, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        except sqlite3.IntegrityError:
            return False
        return True

def get_experiment_samples(experiment_id: str) -> list[dict[str, str]]:
    """Return all samples associated with an experiment."""
    with _connect() as db:
        return [dict(r) for r in db.execute(
            """SELECT s.*, es.role, es.added_at FROM experiment_samples es
            JOIN samples s ON s.sample_id = es.sample_id WHERE es.experiment_id = ? ORDER BY es.added_at""",
            (experiment_id,))]
def create_project(name: str, description: str = "", owner: str = "") -> str:
    """Create a new research project and return its ID."""
    name = name.strip()
    if not name: raise ValueError("Project name is required.")
    pid = "PRJ-" + uuid.uuid4().hex[:10].upper()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as db:
        db.execute("""INSERT INTO projects
            (project_id,name,description,owner,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)""", (pid, name, description, owner.strip(), "active", now, now))
    return pid

def load_projects() -> list[dict[str, str]]:
    """Return all projects newest first."""
    with _connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM projects ORDER BY created_at DESC")]

def get_project(project_id: str) -> dict[str, str] | None:
    """Return a single project by ID, or None if not found."""
    with _connect() as db:
        r = db.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        return dict(r) if r else None

def add_result(experiment_id: str, name: str, description: str = "", result_type: str = "observation",
               data: dict[str, Any] | None = None, status: str = "pending") -> str:
    """Add a result to an experiment and return its ID."""
    name = name.strip()
    if not name: raise ValueError("Result name is required.")
    if status not in RESULT_STATUSES: raise ValueError(f"Invalid result status: {status}")
    with _connect() as db:
        if not db.execute("SELECT 1 FROM experiments WHERE experiment_id = ?", (experiment_id,)).fetchone():
            raise ValueError(f"Experiment {experiment_id} not found.")
    rid = "RES-" + uuid.uuid4().hex[:10].upper()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as db:
        db.execute("""INSERT INTO results
            (result_id,experiment_id,name,description,result_type,data_json,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (rid, experiment_id, name, description, result_type, json.dumps(data or {}), status, now, now))
    return rid

def load_results(experiment_id: str | None = None) -> list[dict[str, Any]]:
    """Return results, optionally filtered by experiment."""
    with _connect() as db:
        if experiment_id:
            rows = db.execute("SELECT * FROM results WHERE experiment_id = ? ORDER BY created_at DESC", (experiment_id,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM results ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

def register_dataset(name: str, description: str = "", project_id: str = "", file_path: str = "",
                     file_type: str = "", row_count: int = 0, column_count: int = 0,
                     validation_status: str = "pending") -> str:
    """Register a dataset and return its ID."""
    name = name.strip()
    if not name: raise ValueError("Dataset name is required.")
    did = "DS-" + uuid.uuid4().hex[:10].upper()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _connect() as db:
        db.execute("""INSERT INTO datasets
            (dataset_id,name,description,project_id,file_path,file_type,row_count,column_count,
             validation_status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (did, name, description, project_id.strip(), file_path, file_type, row_count, column_count,
             validation_status, now, now))
    return did

def load_datasets() -> list[dict[str, Any]]:
    """Return all datasets newest first."""
    with _connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM datasets ORDER BY created_at DESC")]

def get_lab_stats() -> dict[str, int]:
    """Return summary statistics for the laboratory module."""
    with _connect() as db:
        return {
            "samples": db.execute("SELECT COUNT(*) FROM samples").fetchone()[0],
            "experiments": db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0],
            "projects": db.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
            "datasets": db.execute("SELECT COUNT(*) FROM datasets").fetchone()[0],
            "results": db.execute("SELECT COUNT(*) FROM results").fetchone()[0],
        }