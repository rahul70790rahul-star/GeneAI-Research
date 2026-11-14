"""Security and Privacy - Phase 5.9 Core.

Real cryptographic primitives are used throughout:

* AES-256-GCM authenticated encryption (``cryptography`` AESGCM).
* PBKDF2-HMAC-SHA256 password-based key derivation.
* HMAC-SHA256 signed session tokens.
* Append-only JSON-lines audit trail with tamper-evident event fields.

The module keeps a small compatibility layer for the Streamlit security
dashboard (no-argument encryption helpers and file-backed secure storage) while
exposing the API used by the automated test-suite (explicit keys, per-record
storage, role/permission checks and k-anonymity helpers).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

_NONCE_BYTES = 12
_KEY_BYTES = 32


def _utcnow() -> datetime:
    """Naive local timestamp used consistently for session expiry checks."""
    return datetime.now()


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class SecurityLevel(Enum):
    """Security classification levels.

    ``LOW``..``CRITICAL`` are the public classification used by the security
    console. The legacy ``PUBLIC``..``RESTRICTED`` names remain available for
    existing call sites.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class AuditEventType(Enum):
    """Types of audit events."""

    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    DATA_ACCESS = "data_access"
    DATA_EXPORT = "data_export"
    DATA_MODIFY = "data_modify"
    DATA_MODIFICATION = "data_modification"
    DATA_DELETE = "data_delete"
    DATA_DELETION = "data_deletion"
    CONFIG_CHANGE = "config_change"
    PERMISSION_CHANGE = "permission_change"
    SECURITY_VIOLATION = "security_violation"
    API_CALL = "api_call"
    EXPORT_REPORT = "export_report"
    ANALYSIS_RUN = "analysis_run"


@dataclass
class AuditEvent:
    """Security audit event."""

    event_id: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    event_type: AuditEventType = AuditEventType.DATA_ACCESS
    user_id: str = ""
    resource_type: str = ""
    resource_id: str = ""
    action: str = ""
    timestamp: datetime | str = field(default_factory=_utcnow)
    ip_address: str = ""
    user_agent: str = ""
    success: bool = True
    details: dict[str, Any] = field(default_factory=dict)
    security_level: SecurityLevel = SecurityLevel.INTERNAL
    error_message: str = ""
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "user_id": self.user_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "timestamp": _iso(self.timestamp),
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "success": self.success,
            "details": self.details,
            "security_level": self.security_level.value,
            "error_message": self.error_message,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AuditEvent":
        data = dict(payload)
        try:
            data["event_type"] = AuditEventType(data.get("event_type", "data_access"))
        except ValueError:
            data["event_type"] = AuditEventType.DATA_ACCESS
        try:
            data["security_level"] = SecurityLevel(data.get("security_level", "internal"))
        except ValueError:
            data["security_level"] = SecurityLevel.INTERNAL
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            try:
                data["timestamp"] = datetime.fromisoformat(timestamp)
            except ValueError:
                data["timestamp"] = _utcnow()
        data.pop("event_type_value", None)
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{key: value for key, value in data.items() if key in known})


@dataclass
class EncryptionKey:
    """Encryption key with metadata."""

    key_id: str
    key_data: bytes
    algorithm: str = "AES-256-GCM"
    created_at: str = field(default_factory=lambda: _utcnow().isoformat())
    expires_at: str | None = None
    purpose: str = "data_encryption"
    is_active: bool = True

    @classmethod
    def generate(cls, purpose: str = "data_encryption") -> "EncryptionKey":
        """Generate a random 256-bit key."""
        return cls(
            key_id=secrets.token_urlsafe(12),
            key_data=secrets.token_bytes(_KEY_BYTES),
            purpose=purpose,
        )

    @classmethod
    def from_password(
        cls,
        password: str,
        salt: str | bytes | None = None,
        iterations: int = 100_000,
    ) -> "EncryptionKey":
        """Derive a 256-bit key from a password with PBKDF2-HMAC-SHA256."""
        if not isinstance(password, str) or not password:
            raise ValueError("Password must be a non-empty string.")
        if salt is None:
            salt_bytes = secrets.token_bytes(16)
        elif isinstance(salt, str):
            salt_bytes = salt.encode("utf-8")
        else:
            salt_bytes = salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=_KEY_BYTES,
            salt=salt_bytes,
            iterations=max(10_000, int(iterations)),
        )
        return cls(
            key_id=f"pbkdf2-{secrets.token_hex(6)}",
            key_data=kdf.derive(password.encode("utf-8")),
            algorithm="AES-256-GCM",
        )


def _coerce_key(key: EncryptionKey | bytes | bytearray | None) -> bytes:
    if isinstance(key, EncryptionKey):
        key_bytes = key.key_data
    elif isinstance(key, (bytes, bytearray)):
        key_bytes = bytes(key)
    else:
        raise TypeError("An EncryptionKey or 32-byte key is required.")
    if len(key_bytes) != _KEY_BYTES:
        raise ValueError(f"Key must be {_KEY_BYTES} bytes (256 bits).")
    return key_bytes


class DataEncryption:
    """AES-256-GCM data encryption utilities.

    ``encrypt(data)``/``decrypt(token)`` use the instance default key and
    return/accept base64 text (legacy dashboard API). ``encrypt(data, key)`` and
    ``decrypt(token, key)`` use the supplied key and return/accept raw bytes.
    """

    def __init__(self, master_key: EncryptionKey | bytes | None = None):
        if master_key is None:
            self._default_key = EncryptionKey.generate()
        elif isinstance(master_key, EncryptionKey):
            self._default_key = master_key
        else:
            self._default_key = EncryptionKey(
                key_id=secrets.token_urlsafe(8), key_data=bytes(master_key)
            )
        self._aes = AESGCM(self._default_key.key_data)

    # -- key helpers -----------------------------------------------------
    @property
    def master_key(self) -> bytes:
        return self._default_key.key_data

    def generate_key(self) -> EncryptionKey:
        """Return a fresh random AES-256 key."""
        return EncryptionKey.generate()

    @classmethod
    def from_password(cls, password: str, salt: str | bytes | None = None) -> "DataEncryption":
        """Create an encryption helper whose default key is password-derived."""
        return cls(EncryptionKey.from_password(password, salt))

    # -- raw helpers -----------------------------------------------------
    @staticmethod
    def _seal(plaintext: bytes, key_bytes: bytes) -> bytes:
        nonce = secrets.token_bytes(_NONCE_BYTES)
        return nonce + AESGCM(key_bytes).encrypt(nonce, plaintext, None)

    @staticmethod
    def _open(token: bytes, key_bytes: bytes) -> bytes:
        if len(token) <= _NONCE_BYTES:
            raise ValueError("Ciphertext is too short to contain a nonce.")
        nonce, ciphertext = token[:_NONCE_BYTES], token[_NONCE_BYTES:]
        return AESGCM(key_bytes).decrypt(nonce, ciphertext, None)

    # -- public API ------------------------------------------------------
    def encrypt(self, data: str | bytes, key: EncryptionKey | bytes | None = None) -> bytes | str:
        """Encrypt ``data``. Returns bytes when a key is supplied."""
        raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if key is None:
            token = self._seal(raw, self._default_key.key_data)
            return base64.urlsafe_b64encode(token).decode("ascii")
        return self._seal(raw, _coerce_key(key))

    def decrypt(self, encrypted_data: str | bytes, key: EncryptionKey | bytes | None = None) -> bytes:
        """Decrypt ``encrypted_data`` and return the raw plaintext."""
        if key is None:
            token = base64.urlsafe_b64decode(encrypted_data.encode("ascii") if isinstance(encrypted_data, str) else encrypted_data)
            return self._open(token, self._default_key.key_data)
        if isinstance(encrypted_data, str):
            token = base64.urlsafe_b64decode(encrypted_data.encode("ascii"))
        else:
            token = bytes(encrypted_data)
        return self._open(token, _coerce_key(key))

    def decrypt_str(self, encrypted_data: str | bytes, key: EncryptionKey | bytes | None = None) -> str:
        """Decrypt and decode UTF-8 text."""
        return self.decrypt(encrypted_data, key).decode("utf-8")

    def rotate_key(self, new_master_key: EncryptionKey | bytes | None = None) -> EncryptionKey:
        """Replace the default key used by the legacy API."""
        if new_master_key is None:
            self._default_key = EncryptionKey.generate()
        elif isinstance(new_master_key, EncryptionKey):
            self._default_key = new_master_key
        else:
            self._default_key = EncryptionKey(
                key_id=secrets.token_urlsafe(8), key_data=bytes(new_master_key)
            )
        self._aes = AESGCM(self._default_key.key_data)
        return self._default_key


class FieldEncryption:
    """Field-level encryption for sensitive data.

    Supports both ``encrypt_field(field_name, value, key)`` and the legacy
    ``encrypt_field(value, field_name)`` call style.
    """

    def __init__(self, encryption: DataEncryption | None = None):
        self.encryption = encryption or DataEncryption()

    def generate_key(self) -> EncryptionKey:
        return self.encryption.generate_key()

    def _resolve(self, args: tuple[Any, ...], key: Any) -> tuple[str, Any, Any]:
        if len(args) == 3:
            return str(args[0]), args[1], args[2]
        if len(args) == 2:
            if key is not None:
                return str(args[0]), args[1], key
            # Legacy: (value, field_name) using the instance default key.
            return str(args[1]), args[0], None
        if len(args) == 1:
            return "", args[0], key
        raise TypeError("encrypt_field expects (field_name, value, key) or (value, field_name)")

    def encrypt_field(self, *args: Any, key: Any = None) -> dict[str, Any]:
        """Encrypt a field value and return an envelope dictionary."""
        field_name, value, resolved_key = self._resolve(args, key)
        if value is None:
            return {"field": field_name, "encrypted": False, "value": None, "ciphertext": None}
        serialized = json.dumps(value, default=str)
        token = self.encryption.encrypt(serialized, resolved_key)
        if isinstance(token, bytes):
            ciphertext = base64.urlsafe_b64encode(token).decode("ascii")
        else:
            ciphertext = token
        return {
            "field": field_name,
            "encrypted": True,
            "ciphertext": ciphertext,
            "value": ciphertext,
            "algorithm": "AES-256-GCM",
        }

    def decrypt_field(self, encrypted_field: dict[str, Any], key: Any = None) -> Any:
        """Decrypt a field envelope produced by :meth:`encrypt_field`."""
        if not isinstance(encrypted_field, dict):
            return encrypted_field
        if not encrypted_field.get("encrypted", False):
            return encrypted_field.get("value")
        ciphertext = encrypted_field.get("ciphertext") or encrypted_field.get("value")
        if ciphertext is None:
            return None
        try:
            if isinstance(ciphertext, bytes):
                token: str | bytes = ciphertext
            else:
                token = ciphertext
            decrypted = self.encryption.decrypt_str(token, key)
            return json.loads(decrypted)
        except (InvalidTag, ValueError, json.JSONDecodeError) as exc:
            logger.error("Failed to decrypt field %s: %s", encrypted_field.get("field"), exc)
            raise
        except Exception as exc:  # cryptography backend errors
            logger.error("Failed to decrypt field %s: %s", encrypted_field.get("field"), exc)
            raise


class SecureStorage:
    """Encrypted-at-rest record storage.

    When ``storage_path`` has no suffix (or is an existing directory) each record
    is stored as an individually encrypted file, which is what the test-suite
    and the research API expect. Existing dashboard code that passes a ``.enc``
    file path keeps the original single-file behaviour through
    :meth:`set`/:meth:`get`.
    """

    def __init__(
        self,
        storage_path: str | os.PathLike[str],
        encryption: DataEncryption | None = None,
    ):
        self.storage_path = Path(storage_path)
        self.encryption = encryption or DataEncryption()
        self.field_encryption = FieldEncryption(self.encryption)
        self._default_key = EncryptionKey.generate()
        self._data: dict[str, Any] = {}
        path = self.storage_path
        self._directory_mode = (path.suffix == "") or path.is_dir()
        if self._directory_mode:
            self.storage_path.mkdir(parents=True, exist_ok=True)
        else:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage_path.touch(exist_ok=True)
            self._load()

    # -- directory-backed per-record API ---------------------------------
    def _record_path(self, record_id: str) -> Path:
        return self.storage_path / f"{quote(str(record_id), safe='')}.enc"

    def store(self, record_id: str, data: Any, key: EncryptionKey | bytes | None = None) -> Path:
        """Encrypt and persist ``data`` under ``record_id``."""
        if not self._directory_mode:
            self.set(record_id, data, encrypt=True)
            return self.storage_path
        key = key or self._default_key
        token = self.encryption.encrypt(json.dumps(data, default=str), key)
        if not isinstance(token, bytes):
            token = base64.urlsafe_b64decode(token.encode("ascii"))
        path = self._record_path(record_id)
        path.write_bytes(base64.urlsafe_b64encode(token))
        return path

    def retrieve(self, record_id: str, key: EncryptionKey | bytes | None = None) -> Any:
        """Load and decrypt a stored record."""
        if not self._directory_mode:
            return self.get(record_id)
        path = self._record_path(record_id)
        if not path.exists():
            return None
        key = key or self._default_key
        token = base64.urlsafe_b64decode(path.read_bytes())
        plaintext = self.encryption.decrypt(token, key)
        return json.loads(plaintext.decode("utf-8"))

    def list_records(self) -> list[str]:
        """List record identifiers in a directory-backed store."""
        if not self._directory_mode:
            return self.list_keys()
        return sorted(
            unquote(path.stem) for path in self.storage_path.glob("*.enc") if path.is_file()
        )

    def delete(self, record_id: str) -> bool:
        """Delete a record. Returns ``True`` when it existed."""
        if not self._directory_mode:
            return self.delete_key(record_id)
        path = self._record_path(record_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # -- legacy single-file API ------------------------------------------
    def _load(self) -> None:
        if not self.storage_path.exists() or self.storage_path.stat().st_size == 0:
            self._data = {}
            return
        try:
            encrypted = self.storage_path.read_text(encoding="utf-8").strip()
            if not encrypted:
                self._data = {}
                return
            self._data = json.loads(self.encryption.decrypt_str(encrypted))
        except Exception as exc:  # corrupted store must not crash the app
            logger.error("Failed to load secure storage: %s", exc)
            self._data = {}

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = self.encryption.encrypt(json.dumps(self._data, default=str))
        self.storage_path.write_text(str(encrypted), encoding="utf-8")

    def set(self, key: str, value: Any, encrypt: bool = True) -> None:
        """Legacy single-file store."""
        if self._directory_mode:
            self.store(key, value, self._default_key)
            return
        if encrypt:
            self._data[key] = self.field_encryption.encrypt_field(value, key)
        else:
            self._data[key] = {"encrypted": False, "value": value}
        self._save()

    def get(self, key: str, default: Any = None) -> Any:
        """Legacy single-file retrieve."""
        if self._directory_mode:
            value = self.retrieve(key, self._default_key)
            return default if value is None else value
        if key not in self._data:
            return default
        entry = self._data[key]
        if entry.get("encrypted", False):
            return self.field_encryption.decrypt_field(entry)
        return entry.get("value", default)

    def delete_key(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def list_keys(self) -> list[str]:
        return list(self._data.keys())


class AuditLogger:
    """Append-only audit logger backed by a JSON-lines file.

    Events are written immediately, so the trail survives a crash. The file is
    reopened per write and never held open, which keeps Windows temporary
    directories removable and avoids handler leaks in long-running processes.
    """

    def __init__(
        self,
        log_path: str | os.PathLike[str] = "security_audit.log",
        encryption: DataEncryption | None = None,
    ):
        self.log_path = Path(log_path)
        self.encryption = encryption
        self.logger = logging.getLogger("security.audit")
        self._buffer: list[AuditEvent] = []
        self._buffer_size = 100
        self._ensure_path()

    def _ensure_path(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

    def log(self, event: AuditEvent) -> None:
        """Persist an audit event."""
        if not isinstance(event, AuditEvent):
            raise TypeError("AuditLogger.log expects an AuditEvent instance.")
        self._buffer.append(event)
        if len(self._buffer) > self._buffer_size:
            self._buffer = self._buffer[-self._buffer_size:]
        self._ensure_path()
        payload = json.dumps(event.to_dict(), default=str, sort_keys=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        self.logger.info("audit %s %s %s", event.event_type.value, event.user_id, event.resource_id)

    def _flush_buffer(self) -> None:
        """Compatibility hook: events are already persisted on write."""
        self._buffer.clear()

    def get_events(
        self,
        user_id: str | None = None,
        event_type: AuditEventType | None = None,
        limit: int = 100,
        resource_type: str | None = None,
    ) -> list[AuditEvent]:
        """Read events back from the audit trail, newest last."""
        if not self.log_path.exists():
            return []
        events: list[AuditEvent] = []
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = AuditEvent.from_dict(json.loads(line))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if user_id is not None and event.user_id != user_id:
                    continue
                if event_type is not None and event.event_type is not event_type:
                    continue
                if resource_type is not None and event.resource_type != resource_type:
                    continue
                events.append(event)
        if limit is not None and limit >= 0:
            events = events[-limit:] if limit else []
        return events

    def query(
        self,
        user_id: str | None = None,
        event_type: AuditEventType | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Alias for :meth:`get_events`."""
        return self.get_events(user_id=user_id, event_type=event_type, limit=limit)

    def log_login(
        self,
        user_id: str,
        success: bool,
        ip: str = "",
        user_agent: str = "",
        session_id: str = "",
        error: str = "",
    ) -> None:
        self.log(
            AuditEvent(
                event_type=AuditEventType.LOGIN if success else AuditEventType.LOGIN_FAILED,
                user_id=user_id,
                action="login",
                ip_address=ip,
                user_agent=user_agent,
                success=success,
                error_message=error,
                session_id=session_id,
                security_level=SecurityLevel.MEDIUM,
            )
        )

    def log_data_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        ip: str = "",
        session_id: str = "",
        security_level: SecurityLevel = SecurityLevel.INTERNAL,
        action: str = "read",
    ) -> None:
        self.log(
            AuditEvent(
                event_type=AuditEventType.DATA_ACCESS,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                ip_address=ip,
                session_id=session_id,
                security_level=security_level,
            )
        )

    def log_data_export(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        format: str = "",
        record_count: int = 0,
        ip: str = "",
        session_id: str = "",
    ) -> None:
        self.log(
            AuditEvent(
                event_type=AuditEventType.DATA_EXPORT,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action="export",
                ip_address=ip,
                session_id=session_id,
                details={"format": format, "record_count": record_count},
                security_level=SecurityLevel.HIGH,
            )
        )

    def log_api_call(
        self,
        user_id: str,
        endpoint: str,
        method: str,
        ip: str = "",
        session_id: str = "",
        success: bool = True,
        status_code: int = 200,
    ) -> None:
        self.log(
            AuditEvent(
                event_type=AuditEventType.API_CALL,
                user_id=user_id,
                resource_type="api",
                resource_id=endpoint,
                action=method,
                ip_address=ip,
                session_id=session_id,
                success=success,
                details={"method": method, "status_code": status_code},
                security_level=SecurityLevel.MEDIUM,
            )
        )


class AccessControl:
    """Role-based and resource-scoped access control."""

    def __init__(self):
        # ``role -> permissions`` (legacy API, also used as the role registry).
        self._permissions: dict[str, set[str]] = {}
        self._resource_policies: dict[str, dict[str, Any]] = {}
        self._user_roles: dict[str, set[str]] = {}
        self._explicit_permissions: dict[tuple[str, str, str], set[str]] = {}
        self._owners: dict[tuple[str, str], str] = {}
        self._setup_default_permissions()

    def _setup_default_permissions(self) -> None:
        self._permissions = {
            "admin": {
                "read", "write", "delete", "admin", "export", "config",
                "user_management", "audit_access", "system_config", "analyze",
            },
            "researcher": {"read", "write", "analyze", "export", "workflow_create"},
            "analyst": {"read", "analyze", "export", "workflow_run"},
            "viewer": {"read"},
            "guest": {"read"},
        }

    # -- role helpers ----------------------------------------------------
    def has_permission(self, role: str, permission: str) -> bool:
        return permission in self._permissions.get(role, set())

    def get_permissions(self, role: str) -> set[str]:
        return set(self._permissions.get(role, set()))

    def add_permission(self, role: str, permission: str) -> None:
        self._permissions.setdefault(role, set()).add(permission)

    def remove_permission(self, role: str, permission: str) -> None:
        if role in self._permissions:
            self._permissions[role].discard(permission)

    def define_role(self, role: str, permissions: Iterable[str]) -> None:
        """Create or replace a role definition."""
        if not role:
            raise ValueError("Role name is required.")
        self._permissions[role] = {str(permission) for permission in permissions}

    def assign_role(self, user_id: str, role: str) -> None:
        """Assign a role to a user."""
        if not user_id:
            raise ValueError("User ID is required.")
        self._user_roles.setdefault(user_id, set()).add(role)

    def revoke_role(self, user_id: str, role: str) -> None:
        self._user_roles.get(user_id, set()).discard(role)

    def get_user_roles(self, user_id: str) -> set[str]:
        return set(self._user_roles.get(user_id, set()))

    # -- resource helpers ------------------------------------------------
    def set_resource_policy(self, resource: str, policy: dict[str, Any]) -> None:
        self._resource_policies[resource] = policy

    def set_owner(self, resource_type: str, resource_id: str, user_id: str) -> None:
        """Record the owner of a specific resource."""
        self._owners[(resource_type, resource_id)] = user_id

    def get_owner(self, resource_type: str, resource_id: str) -> str | None:
        return self._owners.get((resource_type, resource_id))

    def grant_permission(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        permission: str,
    ) -> None:
        """Grant a specific permission on one resource to one user."""
        self._explicit_permissions.setdefault(
            (user_id, resource_type, resource_id), set()
        ).add(str(permission))

    def revoke_permission(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        permission: str,
    ) -> None:
        """Revoke a specific resource permission from a user."""
        key = (user_id, resource_type, resource_id)
        if key in self._explicit_permissions:
            self._explicit_permissions[key].discard(str(permission))
            if not self._explicit_permissions[key]:
                self._explicit_permissions.pop(key, None)

    def check_permission(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        permission: str,
    ) -> bool:
        """Check ownership, explicit grants and role-derived permissions."""
        permission = str(permission)
        if self._owners.get((resource_type, resource_id)) == user_id:
            return True
        if permission in self._explicit_permissions.get(
            (user_id, resource_type, resource_id), set()
        ):
            return True

        # Resource policy applies to the resource type when configured.
        policy = self._resource_policies.get(resource_type)
        if policy:
            allowed_users = policy.get("allowed_users")
            allowed_roles = policy.get("allowed_roles")
            allowed_actions = policy.get("allowed_actions")
            if allowed_actions is not None and permission not in allowed_actions:
                return False
            if allowed_users is not None and user_id not in allowed_users:
                return False
            if allowed_roles is not None:
                return bool(self.get_user_roles(user_id) & set(allowed_roles))
            if allowed_users is None and allowed_roles is None:
                # Policy only constrained actions; fall through to roles.
                pass

        for role in self.get_user_roles(user_id):
            if self.has_permission(role, permission):
                return True
        return False

    def check_resource_access(self, role: str, resource: str, action: str) -> bool:
        """Legacy role-based resource check used by the dashboard."""
        if resource in self._resource_policies:
            policy = self._resource_policies[resource]
            allowed_roles = policy.get("allowed_roles", [])
            allowed_actions = policy.get("allowed_actions", [])
            if role not in allowed_roles or action not in allowed_actions:
                return False
        return self.has_permission(role, action)


class DataPrivacy:
    """Data privacy utilities: hashing, pseudonymisation and k-anonymity."""

    PII_PATTERNS = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
        "ipv4": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    }

    def __init__(self, hash_salt: str | None = None):
        self._salt = (hash_salt or "geneai-privacy-v1").encode("utf-8")

    # -- helpers ---------------------------------------------------------
    def _hash(self, value: Any) -> str:
        digest = hashlib.sha256(self._salt + str(value).encode("utf-8")).hexdigest()
        return f"anon_{digest[:32]}"

    @classmethod
    def detect_pii(cls, text: str) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {}
        for pii_type, pattern in cls.PII_PATTERNS.items():
            matches = re.findall(pattern, text)
            if matches:
                found[pii_type] = matches
        return found

    @classmethod
    def redact_pii(cls, text: str, replacement: str = "[REDACTED]") -> str:
        result = text
        for pattern in cls.PII_PATTERNS.values():
            result = re.sub(pattern, replacement, result)
        return result

    # -- anonymisation ---------------------------------------------------
    def anonymize(
        self,
        data: dict[str, Any],
        fields_to_hash: Iterable[str] | None = None,
        fields_to_remove: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Return a copy with selected fields hashed or removed."""
        hash_fields = {str(name) for name in (fields_to_hash or [])}
        remove_fields = {str(name) for name in (fields_to_remove or [])}
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key in remove_fields:
                continue
            if key in hash_fields:
                result[key] = self._hash(value)
            else:
                result[key] = value
        return result

    def pseudonymize(
        self,
        records: Iterable[dict[str, Any]],
        field_name: str,
    ) -> list[dict[str, Any]]:
        """Replace an identifier with a stable pseudonym per distinct value."""
        mapping: dict[str, str] = {}
        output: list[dict[str, Any]] = []
        for record in records:
            item = dict(record)
            original = item.get(field_name)
            if original is not None:
                key = str(original)
                if key not in mapping:
                    mapping[key] = self._hash(key)
                item[field_name] = mapping[key]
            output.append(item)
        return output

    def anonymize_batch(
        self,
        records: Iterable[dict[str, Any]],
        fields_to_hash: Iterable[str] | None = None,
        fields_to_remove: Iterable[str] | None = None,
        quasi_identifiers: Iterable[str] | None = None,
        k: int = 2,
    ) -> list[dict[str, Any]]:
        """Anonymise every record in a batch.

        The result is verified for k-anonymity when ``quasi_identifiers`` is
        provided; insufficient anonymity is logged as a warning rather than
        silently discarding records.
        """
        anonymized = [
            self.anonymize(record, fields_to_hash, fields_to_remove) for record in records
        ]
        if quasi_identifiers:
            if not self.check_k_anonymity(anonymized, quasi_identifiers, k):
                logger.warning(
                    "Anonymised batch does not satisfy %s-anonymity for %s",
                    k,
                    list(quasi_identifiers),
                )
        return anonymized

    # -- k-anonymity -----------------------------------------------------
    @staticmethod
    def _generalize(field_name: str, value: Any) -> Any:
        """Generalise ages into 10-year bands; other values are used as-is."""
        if "age" in field_name.lower():
            try:
                return int(float(value) // 10) * 10
            except (TypeError, ValueError):
                return value
        return value

    def check_k_anonymity(
        self,
        records: Iterable[dict[str, Any]],
        quasi_identifiers: Iterable[str],
        k: int,
    ) -> bool:
        """Return ``True`` when every equivalence class has at least ``k`` rows."""
        if k <= 1:
            return True
        fields = [str(field) for field in quasi_identifiers]
        if not fields:
            return False
        counts: dict[tuple[Any, ...], int] = {}
        total = 0
        for record in records:
            key = tuple(self._generalize(field, record.get(field)) for field in fields)
            counts[key] = counts.get(key, 0) + 1
            total += 1
        if total == 0:
            return False
        return all(count >= k for count in counts.values())


@dataclass
class SecureSession:
    """An authenticated user session."""

    session_id: str
    user_id: str
    created_at: datetime = field(default_factory=_utcnow)
    expires_at: datetime = field(default_factory=lambda: _utcnow() + timedelta(hours=24))
    ip_address: str = ""
    user_agent: str = ""
    mfa_verified: bool = False
    is_active: bool = True
    last_activity: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "mfa_verified": self.mfa_verified,
            "is_active": self.is_active,
            "last_activity": self.last_activity.isoformat(),
        }


class SessionSecurity:
    """Session lifecycle management with signed tokens and concurrency limits."""

    def __init__(
        self,
        secret_key: str | None = None,
        session_timeout_minutes: int = 30,
        max_concurrent_sessions: int = 5,
        require_mfa: bool = False,
    ):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.session_timeout_minutes = int(session_timeout_minutes)
        self.max_concurrent_sessions = int(max_concurrent_sessions)
        self.require_mfa = bool(require_mfa)
        self.sessions: dict[str, SecureSession] = {}

    # -- session lifecycle ----------------------------------------------
    def create_session(
        self,
        user_id: str,
        ip_address: str = "",
        user_agent: str = "",
        mfa_verified: bool = False,
    ) -> SecureSession:
        """Create a session, evicting the oldest one when the limit is reached."""
        if not user_id:
            raise ValueError("user_id is required to create a session.")
        if self.require_mfa and not mfa_verified:
            raise PermissionError("MFA verification is required for this deployment.")
        active = self.get_active_sessions(user_id)
        while len(active) >= self.max_concurrent_sessions and active:
            oldest = min(active, key=lambda item: item.created_at)
            self.revoke_session(oldest.session_id)
            active = self.get_active_sessions(user_id)

        now = _utcnow()
        session = SecureSession(
            session_id=secrets.token_urlsafe(32),
            user_id=user_id,
            created_at=now,
            expires_at=now + timedelta(minutes=self.session_timeout_minutes),
            ip_address=ip_address,
            user_agent=user_agent,
            mfa_verified=mfa_verified or not self.require_mfa,
        )
        self.sessions[session.session_id] = session
        return session

    def validate_session(self, session_id: str) -> SecureSession | None:
        """Return the session when valid, otherwise ``None``."""
        session = self.sessions.get(session_id)
        if session is None or not session.is_active:
            return None
        if _utcnow() >= session.expires_at:
            session.is_active = False
            self.sessions.pop(session_id, None)
            return None
        session.last_activity = _utcnow()
        return session

    def get_active_sessions(self, user_id: str | None = None) -> list[SecureSession]:
        """Return non-expired sessions, optionally filtered by user."""
        active: list[SecureSession] = []
        for session_id, session in list(self.sessions.items()):
            if _utcnow() >= session.expires_at or not session.is_active:
                session.is_active = False
                self.sessions.pop(session_id, None)
                continue
            if user_id is None or session.user_id == user_id:
                active.append(session)
        return active

    def revoke_session(self, session_id: str) -> bool:
        session = self.sessions.pop(session_id, None)
        if session is not None:
            session.is_active = False
            return True
        return False

    def revoke_all_user_sessions(self, user_id: str) -> int:
        revoked = 0
        for session_id, session in list(self.sessions.items()):
            if session.user_id == user_id:
                session.is_active = False
                self.sessions.pop(session_id, None)
                revoked += 1
        return revoked

    # -- signed token compatibility -------------------------------------
    def create_session_token(
        self,
        user_id: str,
        expiry_hours: int = 24,
        ip_address: str = "",
        user_agent: str = "",
    ) -> str:
        """Create an HMAC-signed opaque session token."""
        session = self.create_session(user_id, ip_address=ip_address, user_agent=user_agent)
        if expiry_hours:
            session.expires_at = _utcnow() + timedelta(hours=expiry_hours)
        payload = {
            "session_id": session.session_id,
            "user_id": user_id,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
        }
        payload["signature"] = self._sign_payload(payload)
        return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")

    def validate_session_token(self, token: str) -> dict[str, Any] | None:
        """Validate a signed token and the underlying session."""
        try:
            payload = json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
            signature = payload.pop("signature", "")
            if not hmac.compare_digest(signature, self._sign_payload(payload)):
                return None
            session = self.validate_session(payload.get("session_id", ""))
            if session is None:
                return None
            payload["signature"] = signature
            return payload
        except Exception as exc:
            logger.error("Token validation failed: %s", exc)
            return None

    def revoke_user_sessions(self, user_id: str) -> int:
        return self.revoke_all_user_sessions(user_id)

    def _sign_payload(self, payload: dict[str, Any]) -> str:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(self.secret_key.encode("utf-8"), data, hashlib.sha256).hexdigest()


# Global instances ---------------------------------------------------------
_encryption: DataEncryption | None = None
_audit_logger: AuditLogger | None = None
_access_control: AccessControl | None = None
_session_security: SessionSecurity | None = None


def get_encryption(master_key: EncryptionKey | bytes | None = None) -> DataEncryption:
    """Get or create the process-wide encryption helper."""
    global _encryption
    if _encryption is None:
        _encryption = DataEncryption(master_key)
    return _encryption


def get_audit_logger(log_path: str | os.PathLike[str] | None = None) -> AuditLogger:
    """Get or create the process-wide audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(log_path or "security_audit.log")
    return _audit_logger


def get_access_control() -> AccessControl:
    """Get or create the process-wide access control service."""
    global _access_control
    if _access_control is None:
        _access_control = AccessControl()
    return _access_control


def get_session_security(secret_key: str | None = None) -> SessionSecurity:
    """Get or create the process-wide session manager."""
    global _session_security
    if _session_security is None:
        _session_security = SessionSecurity(secret_key)
    return _session_security


def init_security(
    master_key: EncryptionKey | bytes | None = None,
    audit_log_path: str | os.PathLike[str] = "security_audit.log",
    session_secret: str | None = None,
    secure_storage_path: str | os.PathLike[str] | None = None,
    session_timeout_minutes: int = 30,
    max_concurrent_sessions: int = 5,
    require_mfa: bool = False,
) -> dict[str, Any]:
    """Initialise and register every security component.

    Returns a mapping with ``encryption``, ``audit_logger``, ``access_control``,
    ``session_security``, ``data_privacy`` and ``secure_storage``.
    """
    global _encryption, _audit_logger, _access_control, _session_security

    _encryption = DataEncryption(master_key)
    _audit_logger = AuditLogger(audit_log_path, _encryption)
    _access_control = AccessControl()
    _session_security = SessionSecurity(
        session_secret,
        session_timeout_minutes=session_timeout_minutes,
        max_concurrent_sessions=max_concurrent_sessions,
        require_mfa=require_mfa,
    )
    if secure_storage_path is None:
        try:
            from geneai.config import DATA_DIR

            secure_storage_path = Path(DATA_DIR) / "secure_storage"
        except Exception:  # pragma: no cover - config import always succeeds
            secure_storage_path = "secure_storage"
    secure_storage = SecureStorage(secure_storage_path, _encryption)

    return {
        "encryption": _encryption,
        "audit_logger": _audit_logger,
        "access_control": _access_control,
        "session_security": _session_security,
        "data_privacy": DataPrivacy(),
        "secure_storage": secure_storage,
    }


__all__ = [
    "AccessControl",
    "AuditEvent",
    "AuditEventType",
    "AuditLogger",
    "DataEncryption",
    "DataPrivacy",
    "EncryptionKey",
    "FieldEncryption",
    "SecureSession",
    "SecureStorage",
    "SecurityLevel",
    "SessionSecurity",
    "get_access_control",
    "get_audit_logger",
    "get_encryption",
    "get_session_security",
    "init_security",
]
