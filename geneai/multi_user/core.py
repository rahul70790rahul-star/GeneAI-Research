
"""Multi-User Research Platform - Phase 5.5 Core.

Authentication, teams, projects, invitations, sessions and activity logging
backed by SQLite.

All database access uses short-lived connections that are closed before the
call returns. That keeps the database file unlocked between operations, which
matters on Windows where an open handle prevents temporary directories from
being removed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 200_000


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class UserRole(Enum):
    """User roles in the platform."""

    ADMIN = "admin"
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    VIEWER = "viewer"
    GUEST = "guest"

    @property
    def rank(self) -> int:
        return {
            UserRole.GUEST: 0,
            UserRole.VIEWER: 1,
            UserRole.ANALYST: 2,
            UserRole.RESEARCHER: 3,
            UserRole.ADMIN: 4,
        }[self]


class TeamRole(Enum):
    """Roles within a team."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"

    @property
    def rank(self) -> int:
        return {
            TeamRole.VIEWER: 0,
            TeamRole.MEMBER: 1,
            TeamRole.ADMIN: 2,
            TeamRole.OWNER: 3,
        }[self]


class ProjectVisibility(Enum):
    """Project visibility levels."""

    PRIVATE = "private"
    TEAM = "team"
    PUBLIC = "public"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now().isoformat()


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _coerce_enum(enum_type, value, default):
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (ValueError, TypeError):
        return default


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password with PBKDF2-HMAC-SHA256 and a per-user salt."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return digest.hex(), salt


def verify_password_hash(password: str, password_hash: str, salt: str) -> bool:
    if not password_hash or not salt:
        return False
    digest, _ = hash_password(password, salt)
    return hmac.compare_digest(digest, password_hash)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class User:
    """User account."""

    user_id: str
    username: str
    email: str
    password_hash: str = field(default="", repr=False)
    salt: str = field(default="", repr=False)
    role: UserRole = UserRole.RESEARCHER
    full_name: str = ""
    avatar_url: str = ""
    created_at: datetime | str = field(default_factory=_now)
    updated_at: datetime | str = field(default_factory=_now)
    last_login: datetime | str | None = None
    is_active: bool = True
    preferences: dict[str, Any] = field(default_factory=dict)

    @property
    def created_at_iso(self) -> str:
        return _iso(self.created_at)

    def to_dict(self, include_sensitive: bool = False) -> dict[str, Any]:
        data = {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": _coerce_enum(UserRole, self.role, UserRole.RESEARCHER).value,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "last_login": _iso(self.last_login) or None,
            "is_active": self.is_active,
            "preferences": self.preferences,
        }
        if include_sensitive:
            data["password_hash"] = self.password_hash
            data["salt"] = self.salt
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "User":
        return cls(
            user_id=data.get("user_id", ""),
            username=data.get("username", ""),
            email=data.get("email", ""),
            password_hash=data.get("password_hash", ""),
            salt=data.get("salt", ""),
            role=_coerce_enum(UserRole, data.get("role"), UserRole.RESEARCHER),
            full_name=data.get("full_name", ""),
            avatar_url=data.get("avatar_url", ""),
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
            last_login=data.get("last_login"),
            is_active=bool(data.get("is_active", True)),
            preferences=data.get("preferences") or {},
        )


@dataclass
class Team:
    """Research team."""

    team_id: str
    name: str
    description: str = ""
    owner_id: str = ""
    created_at: datetime | str = field(default_factory=_now)
    updated_at: datetime | str = field(default_factory=_now)
    members: dict[str, TeamRole] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "members": {
                key: _coerce_enum(TeamRole, value, TeamRole.MEMBER).value
                for key, value in self.members.items()
            },
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Team":
        return cls(
            team_id=data.get("team_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            owner_id=data.get("owner_id", ""),
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
            members={
                key: _coerce_enum(TeamRole, value, TeamRole.MEMBER)
                for key, value in (data.get("members") or {}).items()
            },
            settings=data.get("settings") or {},
        )


@dataclass
class TeamMember:
    """A user's membership in a team."""

    team_id: str
    user_id: str
    role: TeamRole = TeamRole.MEMBER
    joined_at: datetime | str = field(default_factory=_now)
    username: str = ""
    email: str = ""


@dataclass
class Project:
    """Research project."""

    project_id: str
    name: str
    description: str = ""
    owner_id: str = ""
    team_id: str | None = None
    visibility: ProjectVisibility = ProjectVisibility.PRIVATE
    created_at: datetime | str = field(default_factory=_now)
    updated_at: datetime | str = field(default_factory=_now)
    tags: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
            "team_id": self.team_id,
            "visibility": _coerce_enum(
                ProjectVisibility, self.visibility, ProjectVisibility.PRIVATE
            ).value,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "tags": self.tags,
            "settings": self.settings,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        return cls(
            project_id=data.get("project_id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            owner_id=data.get("owner_id", ""),
            team_id=data.get("team_id") or None,
            visibility=_coerce_enum(
                ProjectVisibility, data.get("visibility"), ProjectVisibility.PRIVATE
            ),
            created_at=data.get("created_at", _now()),
            updated_at=data.get("updated_at", _now()),
            tags=data.get("tags") or [],
            settings=data.get("settings") or {},
            metadata=data.get("metadata") or {},
        )


@dataclass
class Session:
    """User session.

    ``session_token`` is the credential presented by clients; ``session_id``
    is kept as an alias for older call sites.
    """

    session_id: str
    user_id: str
    created_at: datetime | str = field(default_factory=_now)
    expires_at: datetime | str = ""
    ip_address: str = ""
    user_agent: str = ""
    is_active: bool = True
    session_token: str = ""

    def __post_init__(self) -> None:
        if not self.session_token:
            self.session_token = self.session_id
        if not self.session_id:
            self.session_id = self.session_token

    @property
    def is_expired(self) -> bool:
        expires = _parse_dt(self.expires_at)
        return expires is None or datetime.now() > expires

    def is_expired_now(self) -> bool:
        return self.is_expired


@dataclass
class Activity:
    """User activity log."""

    activity_id: str
    user_id: str
    action: str
    resource_type: str = ""
    resource_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    team_id: str | None = None
    ip_address: str = ""
    timestamp: datetime | str = field(default_factory=_now)


@dataclass
class Invitation:
    """Team/project invitation."""

    invitation_id: str
    inviter_id: str = ""
    email: str = ""
    team_id: str | None = None
    project_id: str | None = None
    role: TeamRole = TeamRole.MEMBER
    status: str = "pending"
    created_at: datetime | str = field(default_factory=_now)
    expires_at: datetime | str = ""
    token: str = ""
    invitation_token: str = ""

    def __post_init__(self) -> None:
        if not self.token:
            self.token = secrets.token_urlsafe(24)
        if not self.invitation_token:
            self.invitation_token = self.token
        if not self.token:
            self.token = self.invitation_token

    @property
    def invitee_email(self) -> str:
        return self.email

    @property
    def is_expired(self) -> bool:
        expires = _parse_dt(self.expires_at)
        return expires is not None and datetime.now() > expires


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------
class _DatabaseProxy:
    """Minimal connection proxy.

    ``manager.db.execute(...)``/``manager.db.commit()`` remain available for
    callers that need direct SQL, but each statement uses a connection that is
    closed immediately so the database file is never left locked.
    """

    def __init__(self, manager: "AuthManager"):
        self._manager = manager

    def execute(self, sql: str, params: tuple = ()):
        conn = self._manager._connect()
        try:
            cursor = conn.execute(sql, params)
            conn.commit()
            if sql.strip().split(None, 1)[0].upper() == "SELECT":
                return cursor.fetchall()
            return cursor
        finally:
            conn.close()

    def executescript(self, script: str) -> None:
        conn = self._manager._connect()
        try:
            conn.executescript(script)
            conn.commit()
        finally:
            conn.close()

    def commit(self) -> None:  # statements are committed eagerly
        return None

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Auth manager
# ---------------------------------------------------------------------------
class AuthManager:
    """Authentication and collaboration manager."""

    def __init__(
        self,
        db_path: str | Path = "multi_user.db",
        session_timeout_hours: int = 24,
        invitation_expiry_hours: int = 72,
        create_default_admin: bool = True,
    ):
        self.db_path = Path(db_path)
        self.session_timeout_hours = session_timeout_hours
        self.invitation_expiry_hours = invitation_expiry_hours
        self.db = _DatabaseProxy(self)
        self._init_db()
        if create_default_admin:
            self._ensure_default_admin()

    # -- connections ----------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        """Kept for API symmetry; connections are closed per operation."""

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def _query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        conn = self._connect()
        try:
            return conn.execute(sql, params).fetchone()
        finally:
            conn.close()

    def _execute(self, sql: str, params: tuple = ()) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount if cursor.rowcount != -1 else 0
        finally:
            conn.close()

    # -- schema ---------------------------------------------------------
    def _init_db(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT DEFAULT '',
            avatar_url TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_login TEXT,
            is_active INTEGER DEFAULT 1,
            preferences TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            ip_address TEXT DEFAULT '',
            user_agent TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS teams (
            team_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            owner_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            settings TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS team_members (
            team_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (team_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            owner_id TEXT NOT NULL,
            team_id TEXT,
            visibility TEXT DEFAULT 'private',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            settings TEXT DEFAULT '{}',
            metadata TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS invitations (
            invitation_id TEXT PRIMARY KEY,
            inviter_id TEXT DEFAULT '',
            email TEXT NOT NULL,
            team_id TEXT,
            project_id TEXT,
            role TEXT DEFAULT 'member',
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            invitation_token TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS activities (
            activity_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT DEFAULT '',
            resource_id TEXT DEFAULT '',
            details TEXT DEFAULT '{}',
            team_id TEXT,
            ip_address TEXT DEFAULT '',
            timestamp TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id);
        CREATE INDEX IF NOT EXISTS idx_activities_user ON activities(user_id);
        CREATE INDEX IF NOT EXISTS idx_activities_team ON activities(team_id);
        """
        conn = self._connect()
        try:
            conn.executescript(schema)
            # Migrate databases created before ``invitation_token`` existed.
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(invitations)").fetchall()
            }
            if "invitation_token" not in columns:
                conn.execute("ALTER TABLE invitations ADD COLUMN invitation_token TEXT")
                conn.execute(
                    "UPDATE invitations SET invitation_token = token WHERE invitation_token IS NULL"
                )
            conn.commit()
        finally:
            conn.close()

    def _ensure_default_admin(self) -> None:
        existing = self._query_one(
            "SELECT user_id FROM users WHERE role = ? LIMIT 1", (UserRole.ADMIN.value,)
        )
        if existing is not None:
            return
        password = os.environ.get("GENEAI_ADMIN_PASSWORD") or secrets.token_urlsafe(18)
        try:
            self.create_user(
                username="admin",
                email=os.environ.get("GENEAI_ADMIN_EMAIL", "admin@geneai.local"),
                password=password,
                full_name="Administrator",
                role=UserRole.ADMIN,
            )
        except Exception:  # pragma: no cover - concurrent initialisation
            logger.debug("Default admin already exists", exc_info=True)
            return
        if not os.environ.get("GENEAI_ADMIN_PASSWORD"):
            logger.warning(
                "Created default admin account with a generated password. Set "
                "GENEAI_ADMIN_PASSWORD before first run or reset the password."
            )

    # -- users ----------------------------------------------------------
    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str = "",
        role: UserRole | str = UserRole.RESEARCHER,
    ) -> str:
        if not username or not email or not password:
            raise ValueError("username, email and password are required")
        role = _coerce_enum(UserRole, role, UserRole.RESEARCHER)
        user_id = str(uuid.uuid4())
        password_hash, salt = hash_password(password)
        now = _now()
        self._execute(
            """INSERT INTO users (user_id, username, email, password_hash, salt, role,
               full_name, created_at, updated_at, is_active, preferences)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '{}')""",
            (user_id, username, email, password_hash, salt, role.value, full_name, now, now),
        )
        return user_id

    def _row_to_user(self, row: sqlite3.Row | None) -> User | None:
        if row is None:
            return None
        return User(
            user_id=row["user_id"],
            username=row["username"],
            email=row["email"],
            password_hash=row["password_hash"],
            salt=row["salt"],
            role=_coerce_enum(UserRole, row["role"], UserRole.RESEARCHER),
            full_name=row["full_name"] or "",
            avatar_url=row["avatar_url"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_login=row["last_login"],
            is_active=bool(row["is_active"]),
            preferences=json.loads(row["preferences"] or "{}"),
        )

    def get_user(self, user_id: str) -> User | None:
        return self._row_to_user(
            self._query_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        )

    def get_user_by_email(self, email: str) -> User | None:
        return self._row_to_user(
            self._query_one("SELECT * FROM users WHERE email = ?", (email,))
        )

    def get_user_by_username(self, username: str) -> User | None:
        return self._row_to_user(
            self._query_one("SELECT * FROM users WHERE username = ?", (username,))
        )

    def list_users(
        self, role: UserRole | None = None, active_only: bool = True
    ) -> list[User]:
        sql = "SELECT * FROM users"
        clauses: list[str] = []
        params: list[Any] = []
        if role is not None:
            clauses.append("role = ?")
            params.append(_coerce_enum(UserRole, role, UserRole.RESEARCHER).value)
        if active_only:
            clauses.append("is_active = 1")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at"
        return [
            user
            for user in (self._row_to_user(row) for row in self._query(sql, tuple(params)))
            if user is not None
        ]

    def verify_password(self, user_id: str, password: str) -> bool:
        row = self._query_one(
            "SELECT password_hash, salt FROM users WHERE user_id = ?", (user_id,)
        )
        if row is None:
            return False
        return verify_password_hash(password, row["password_hash"], row["salt"])

    def authenticate(
        self, identifier: str, password: str, expiry_hours: int | None = None
    ) -> Session | None:
        """Authenticate by username or email and return a new session."""
        row = self._query_one(
            "SELECT * FROM users WHERE username = ? OR email = ? LIMIT 1",
            (identifier, identifier),
        )
        if row is None or not row["is_active"]:
            return None
        if not verify_password_hash(password, row["password_hash"], row["salt"]):
            return None
        user_id = row["user_id"]
        now = _now()
        self._execute(
            "UPDATE users SET last_login = ?, updated_at = ? WHERE user_id = ?",
            (now, now, user_id),
        )
        return self.create_session(user_id, expiry_hours=expiry_hours)

    def update_user(self, user_id: str, **kwargs: Any) -> User | None:
        allowed = {
            "email",
            "full_name",
            "avatar_url",
            "role",
            "is_active",
            "preferences",
            "last_login",
        }
        updates: list[str] = []
        params: list[Any] = []
        for key, value in kwargs.items():
            if key not in allowed or value is None:
                continue
            if key == "role":
                value = _coerce_enum(UserRole, value, UserRole.RESEARCHER).value
            elif key == "preferences":
                value = json.dumps(value)
            elif key == "is_active":
                value = 1 if value else 0
            updates.append(f"{key} = ?")
            params.append(value)
        if not updates:
            return self.get_user(user_id)
        updates.append("updated_at = ?")
        params.append(_now())
        params.append(user_id)
        self._execute(f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?", tuple(params))
        return self.get_user(user_id)

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        if not self.verify_password(user_id, old_password):
            return False
        password_hash, salt = hash_password(new_password)
        self._execute(
            "UPDATE users SET password_hash = ?, salt = ?, updated_at = ? WHERE user_id = ?",
            (password_hash, salt, _now(), user_id),
        )
        return True

    def delete_user(self, user_id: str, requester_id: str | None = None) -> bool:
        user = self.get_user(user_id)
        if user is None:
            return False
        if requester_id is not None:
            requester = self.get_user(requester_id)
            if requester is None or requester.role != UserRole.ADMIN:
                return False
        self._execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        return True

    # -- sessions -------------------------------------------------------
    def create_session(
        self,
        user_id: str,
        expiry_hours: int | None = None,
        ip_address: str = "",
        user_agent: str = "",
    ) -> Session:
        token = secrets.token_urlsafe(32)
        session_id = str(uuid.uuid4())
        now = datetime.now()
        expires = now + timedelta(hours=expiry_hours or self.session_timeout_hours)
        self._execute(
            """INSERT INTO sessions (session_id, user_id, session_token, created_at,
               expires_at, ip_address, user_agent, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (session_id, user_id, token, now.isoformat(), expires.isoformat(), ip_address, user_agent),
        )
        return Session(
            session_id=session_id,
            user_id=user_id,
            session_token=token,
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            ip_address=ip_address,
            user_agent=user_agent,
            is_active=True,
        )

    def get_session(self, session_token: str) -> Session | None:
        row = self._query_one(
            "SELECT * FROM sessions WHERE session_token = ? OR session_id = ? LIMIT 1",
            (session_token, session_token),
        )
        if row is None:
            return None
        return Session(
            session_id=row["session_id"],
            user_id=row["user_id"],
            session_token=row["session_token"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            ip_address=row["ip_address"] or "",
            user_agent=row["user_agent"] or "",
            is_active=bool(row["is_active"]),
        )

    def validate_session(self, session_token: str) -> User | None:
        session = self.get_session(session_token)
        if session is None or not session.is_active or session.is_expired:
            return None
        user = self.get_user(session.user_id)
        if user is None or not user.is_active:
            return None
        return user

    def invalidate_session(self, session_token: str) -> bool:
        session = self.get_session(session_token)
        if session is None:
            return False
        self._execute(
            "UPDATE sessions SET is_active = 0 WHERE session_id = ?", (session.session_id,)
        )
        return True

    def invalidate_user_sessions(self, user_id: str) -> int:
        return self._execute(
            "UPDATE sessions SET is_active = 0 WHERE user_id = ? AND is_active = 1",
            (user_id,),
        )

    def cleanup_expired_sessions(self) -> int:
        return self._execute(
            "DELETE FROM sessions WHERE expires_at < ?", (datetime.now().isoformat(),)
        )

    # -- teams ----------------------------------------------------------
    def create_team(
        self,
        name: str,
        description: str = "",
        owner_id: str = "",
        settings: dict[str, Any] | None = None,
    ) -> str:
        if not name:
            raise ValueError("Team name is required")
        team_id = str(uuid.uuid4())
        now = _now()
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO teams (team_id, name, description, owner_id, created_at,
                   updated_at, settings) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (team_id, name, description, owner_id, now, now, json.dumps(settings or {})),
            )
            if owner_id:
                conn.execute(
                    """INSERT OR REPLACE INTO team_members (team_id, user_id, role, joined_at)
                       VALUES (?, ?, ?, ?)""",
                    (team_id, owner_id, TeamRole.OWNER.value, now),
                )
            conn.commit()
        finally:
            conn.close()
        return team_id

    def get_team(self, team_id: str) -> Team | None:
        row = self._query_one("SELECT * FROM teams WHERE team_id = ?", (team_id,))
        if row is None:
            return None
        members: dict[str, TeamRole] = {}
        for member in self._query(
            "SELECT user_id, role FROM team_members WHERE team_id = ?", (team_id,)
        ):
            members[member["user_id"]] = _coerce_enum(TeamRole, member["role"], TeamRole.MEMBER)
        return Team(
            team_id=row["team_id"],
            name=row["name"],
            description=row["description"] or "",
            owner_id=row["owner_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            members=members,
            settings=json.loads(row["settings"] or "{}"),
        )

    def update_team(self, team_id: str, **kwargs: Any) -> Team | None:
        allowed = {"name", "description", "settings"}
        updates: list[str] = []
        params: list[Any] = []
        for key, value in kwargs.items():
            if key not in allowed or value is None:
                continue
            if key == "settings":
                value = json.dumps(value)
            updates.append(f"{key} = ?")
            params.append(value)
        if updates:
            updates.append("updated_at = ?")
            params.extend([_now(), team_id])
            self._execute(f"UPDATE teams SET {', '.join(updates)} WHERE team_id = ?", tuple(params))
        return self.get_team(team_id)

    def add_team_member(
        self, team_id: str, user_id: str, role: TeamRole | str = TeamRole.MEMBER
    ) -> bool:
        if self.get_team(team_id) is None or self.get_user(user_id) is None:
            return False
        role = _coerce_enum(TeamRole, role, TeamRole.MEMBER)
        self._execute(
            """INSERT OR REPLACE INTO team_members (team_id, user_id, role, joined_at)
               VALUES (?, ?, ?, ?)""",
            (team_id, user_id, role.value, _now()),
        )
        return True

    def remove_team_member(
        self,
        team_id: str,
        user_id: str,
        requester_id: str | None = None,
    ) -> bool:
        team = self.get_team(team_id)
        if team is None:
            return False
        if requester_id is not None and requester_id != user_id:
            requester = self.get_user(requester_id)
            requester_role = team.members.get(requester_id)
            is_admin = requester is not None and requester.role == UserRole.ADMIN
            can_manage = requester_role in (TeamRole.OWNER, TeamRole.ADMIN)
            if not (is_admin or can_manage):
                return False
        if user_id == team.owner_id:
            return False
        self._execute(
            "DELETE FROM team_members WHERE team_id = ? AND user_id = ?", (team_id, user_id)
        )
        return True

    def get_team_members(self, team_id: str) -> list[TeamMember]:
        rows = self._query(
            """SELECT tm.team_id, tm.user_id, tm.role, tm.joined_at,
                      u.username, u.email
               FROM team_members tm
               LEFT JOIN users u ON u.user_id = tm.user_id
               WHERE tm.team_id = ?
               ORDER BY CASE tm.role
                   WHEN 'owner' THEN 0 WHEN 'admin' THEN 1
                   WHEN 'member' THEN 2 ELSE 3 END, tm.joined_at""",
            (team_id,),
        )
        return [
            TeamMember(
                team_id=row["team_id"],
                user_id=row["user_id"],
                role=_coerce_enum(TeamRole, row["role"], TeamRole.MEMBER),
                joined_at=row["joined_at"],
                username=row["username"] or "",
                email=row["email"] or "",
            )
            for row in rows
        ]

    def list_user_teams(self, user_id: str) -> list[Team]:
        rows = self._query(
            "SELECT team_id FROM team_members WHERE user_id = ? ORDER BY joined_at",
            (user_id,),
        )
        return [
            team
            for team in (self.get_team(row["team_id"]) for row in rows)
            if team is not None
        ]

    # -- projects -------------------------------------------------------
    def create_project(
        self,
        name: str,
        description: str = "",
        owner_id: str = "",
        team_id: str | None = None,
        visibility: ProjectVisibility | str = ProjectVisibility.PRIVATE,
        tags: list[str] | None = None,
    ) -> str:
        if not name:
            raise ValueError("Project name is required")
        project_id = str(uuid.uuid4())
        now = _now()
        visibility = _coerce_enum(ProjectVisibility, visibility, ProjectVisibility.PRIVATE)
        self._execute(
            """INSERT INTO projects (project_id, name, description, owner_id, team_id,
               visibility, created_at, updated_at, tags, settings, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', '{}')""",
            (
                project_id,
                name,
                description,
                owner_id,
                team_id,
                visibility.value,
                now,
                now,
                json.dumps(tags or []),
            ),
        )
        return project_id

    def get_project(self, project_id: str) -> Project | None:
        row = self._query_one("SELECT * FROM projects WHERE project_id = ?", (project_id,))
        if row is None:
            return None
        return Project(
            project_id=row["project_id"],
            name=row["name"],
            description=row["description"] or "",
            owner_id=row["owner_id"],
            team_id=row["team_id"] or None,
            visibility=_coerce_enum(
                ProjectVisibility, row["visibility"], ProjectVisibility.PRIVATE
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tags=json.loads(row["tags"] or "[]"),
            settings=json.loads(row["settings"] or "{}"),
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def update_project(self, project_id: str, **kwargs: Any) -> Project | None:
        allowed = {"name", "description", "team_id", "visibility", "tags", "settings", "metadata"}
        updates: list[str] = []
        params: list[Any] = []
        for key, value in kwargs.items():
            if key not in allowed or value is None:
                continue
            if key == "visibility":
                value = _coerce_enum(ProjectVisibility, value, ProjectVisibility.PRIVATE).value
            elif key in ("tags", "settings", "metadata"):
                value = json.dumps(value)
            updates.append(f"{key} = ?")
            params.append(value)
        if updates:
            updates.append("updated_at = ?")
            params.extend([_now(), project_id])
            self._execute(
                f"UPDATE projects SET {', '.join(updates)} WHERE project_id = ?", tuple(params)
            )
        return self.get_project(project_id)

    def delete_project(self, project_id: str, requester_id: str | None = None) -> bool:
        project = self.get_project(project_id)
        if project is None:
            return False
        if requester_id is not None and requester_id != project.owner_id:
            requester = self.get_user(requester_id)
            if requester is None or requester.role != UserRole.ADMIN:
                return False
        self._execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
        return True

    def list_projects(self, user_id: str, team_id: str | None = None) -> list[Project]:
        if team_id:
            rows = self._query(
                "SELECT * FROM projects WHERE team_id = ? ORDER BY updated_at DESC", (team_id,)
            )
        else:
            team_ids = [team.team_id for team in self.list_user_teams(user_id)]
            placeholders = ",".join("?" for _ in team_ids)
            sql = "SELECT * FROM projects WHERE owner_id = ? OR visibility = 'public'"
            params: list[Any] = [user_id]
            if team_ids:
                sql += f" OR team_id IN ({placeholders})"
                params.extend(team_ids)
            sql += " ORDER BY updated_at DESC"
            rows = self._query(sql, tuple(params))
        return [
            project
            for project in (self.get_project(row["project_id"]) for row in rows)
            if project is not None
        ]

    def user_can_access_project(self, user_id: str, project_id: str) -> bool:
        project = self.get_project(project_id)
        if project is None or self.get_user(user_id) is None:
            return False
        if project.visibility == ProjectVisibility.PUBLIC:
            return True
        if project.owner_id == user_id:
            return True
        if project.team_id:
            return user_id in (self.get_team(project.team_id).members if self.get_team(project.team_id) else {})
        return False

    # -- invitations ----------------------------------------------------
    def create_invitation(
        self,
        email: str,
        team_id: str | None = None,
        role: TeamRole | str = TeamRole.MEMBER,
        invited_by: str = "",
        project_id: str | None = None,
    ) -> Invitation:
        if not email:
            raise ValueError("email is required")
        invitation_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(24)
        now = datetime.now()
        expires = now + timedelta(hours=self.invitation_expiry_hours)
        role = _coerce_enum(TeamRole, role, TeamRole.MEMBER)
        self._execute(
            """INSERT INTO invitations (invitation_id, inviter_id, email, team_id,
               project_id, role, status, created_at, expires_at, token, invitation_token)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
            (
                invitation_id,
                invited_by,
                email,
                team_id,
                project_id,
                role.value,
                now.isoformat(),
                expires.isoformat(),
                token,
                token,
            ),
        )
        return Invitation(
            invitation_id=invitation_id,
            inviter_id=invited_by,
            email=email,
            team_id=team_id,
            project_id=project_id,
            role=role,
            status="pending",
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            token=token,
            invitation_token=token,
        )

    def _row_to_invitation(self, row: sqlite3.Row | None) -> Invitation | None:
        if row is None:
            return None
        return Invitation(
            invitation_id=row["invitation_id"],
            inviter_id=row["inviter_id"] or "",
            email=row["email"],
            team_id=row["team_id"] or None,
            project_id=row["project_id"] or None,
            role=_coerce_enum(TeamRole, row["role"], TeamRole.MEMBER),
            status=row["status"] or "pending",
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            token=row["token"],
            invitation_token=row["token"],
        )

    def get_invitation_by_token(self, token: str) -> Invitation | None:
        return self._row_to_invitation(
            self._query_one(
                "SELECT * FROM invitations WHERE token = ? OR invitation_token = ? LIMIT 1",
                (token, token),
            )
        )

    def accept_invitation(self, token: str, password: str) -> str | None:
        invitation = self.get_invitation_by_token(token)
        if invitation is None or invitation.status != "pending" or invitation.is_expired:
            return None

        user = self.get_user_by_email(invitation.email)
        if user is None:
            base_username = invitation.email.split("@")[0][:40] or "user"
            username = base_username
            suffix = 1
            while self.get_user_by_username(username) is not None:
                suffix += 1
                username = f"{base_username}{suffix}"
            user_id = self.create_user(
                username=username,
                email=invitation.email,
                password=password,
                full_name=username,
                role=UserRole.RESEARCHER,
            )
        else:
            user_id = user.user_id

        if invitation.team_id:
            self.add_team_member(invitation.team_id, user_id, invitation.role)
        self._execute(
            "UPDATE invitations SET status = 'accepted' WHERE invitation_id = ?",
            (invitation.invitation_id,),
        )
        return user_id

    def list_pending_invitations(self, email: str) -> list[Invitation]:
        rows = self._query(
            "SELECT * FROM invitations WHERE email = ? AND status = 'pending' ORDER BY created_at",
            (email,),
        )
        return [
            invitation
            for invitation in (self._row_to_invitation(row) for row in rows)
            if invitation is not None
        ]

    # -- activity -------------------------------------------------------
    def log_activity(
        self,
        user_id: str,
        action: str,
        resource_type: str = "",
        resource_id: str = "",
        details: dict[str, Any] | None = None,
        team_id: str | None = None,
        ip_address: str = "",
    ) -> str:
        activity_id = str(uuid.uuid4())
        self._execute(
            """INSERT INTO activities (activity_id, user_id, action, resource_type,
               resource_id, details, team_id, ip_address, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                activity_id,
                user_id,
                action,
                resource_type,
                resource_id,
                json.dumps(details or {}),
                team_id,
                ip_address,
                _now(),
            ),
        )
        return activity_id

    def _row_to_activity(self, row: sqlite3.Row) -> Activity:
        return Activity(
            activity_id=row["activity_id"],
            user_id=row["user_id"],
            action=row["action"],
            resource_type=row["resource_type"] or "",
            resource_id=row["resource_id"] or "",
            details=json.loads(row["details"] or "{}"),
            team_id=row["team_id"] or None,
            ip_address=row["ip_address"] or "",
            timestamp=row["timestamp"],
        )

    def get_user_activities(self, user_id: str, limit: int = 50) -> list[Activity]:
        rows = self._query(
            "SELECT * FROM activities WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        )
        return [self._row_to_activity(row) for row in rows]

    def get_team_activities(self, team_id: str, limit: int = 50) -> list[Activity]:
        rows = self._query(
            "SELECT * FROM activities WHERE team_id = ? ORDER BY timestamp DESC LIMIT ?",
            (team_id, limit),
        )
        return [self._row_to_activity(row) for row in rows]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_auth_manager: AuthManager | None = None


def get_auth_manager(db_path: str | Path | None = None) -> AuthManager:
    """Get the global authentication manager."""
    global _auth_manager
    if _auth_manager is None:
        if db_path is None:
            try:
                from geneai.config import DATA_DIR

                db_path = Path(DATA_DIR) / "multi_user.db"
            except Exception:  # pragma: no cover - configuration is available
                db_path = "multi_user.db"
        _auth_manager = AuthManager(db_path=db_path)
    return _auth_manager


__all__ = [
    "Activity",
    "AuthManager",
    "Invitation",
    "Project",
    "ProjectVisibility",
    "Session",
    "Team",
    "TeamMember",
    "TeamRole",
    "User",
    "UserRole",
    "get_auth_manager",
    "hash_password",
    "verify_password_hash",
]
