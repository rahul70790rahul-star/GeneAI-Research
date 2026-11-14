"""Approval management module for Autonomous Bioinformatics Agent."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from geneai.autonomous_agent.database import (
    create_approval_request,
    respond_to_approval,
    get_pending_approvals,
    get_approval_request,
)
from geneai.autonomous_agent.types import ApprovalStatus, ApprovalType

logger = logging.getLogger(__name__)


def _to_datetime(value: Any) -> datetime | None:
    """Convert a stored epoch timestamp or ISO-8601 string to a datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value)
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


@dataclass
class ApprovalRequest:
    """An approval request."""
    approval_id: str
    session_id: str
    task_id: str
    request_type: ApprovalType
    description: str
    parameters: dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime | None = None
    responded_at: datetime | None = None
    responder_id: str | None = None
    response: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ApprovalManager:
    """
    Manage human-in-the-loop approvals for sensitive operations.
    """

    def __init__(self, timeout_hours: int = 24):
        self.timeout_hours = timeout_hours
        self.logger = logging.getLogger(__name__)

    def request_approval(
        self,
        session_id: str,
        task_id: str,
        request_type: ApprovalType,
        description: str,
        parameters: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Create an approval request.

        Args:
            session_id: Session ID
            task_id: Task ID requiring approval
            request_type: Type of approval
            description: Human-readable description
            parameters: Tool parameters (for context)
            metadata: Additional metadata

        Returns:
            Approval request ID
        """
        approval_id = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(hours=self.timeout_hours)

        create_approval_request(
            approval_id=approval_id,
            session_id=session_id,
            task_id=task_id,
            request_type=request_type.value,
            description=description,
            parameters=parameters or {},
            expires_at=expires_at.isoformat(),
            metadata=metadata or {},
        )

        self.logger.info("Created approval request %s for session %s", approval_id, session_id)
        return approval_id

    def respond(
        self,
        approval_id: str,
        response: str,
        responder_id: str,
    ) -> bool:
        """
        Respond to an approval request.

        Args:
            approval_id: Approval request ID
            response: "approved" or "rejected"
            responder_id: ID of person responding

        Returns:
            True if successful
        """
        valid_responses = {"approved", "rejected"}
        if response not in valid_responses:
            self.logger.error("Invalid response: %s", response)
            return False

        success = respond_to_approval(approval_id, response, responder_id)
        if success:
            self.logger.info("Approval %s responded: %s by %s", approval_id, response, responder_id)
        return success

    def get_pending(self, session_id: str) -> list[ApprovalRequest]:
        """Get pending approvals for a session."""
        rows = get_pending_approvals(session_id)
        return [self._row_to_request(row) for row in rows]

    def get_request(self, approval_id: str) -> ApprovalRequest | None:
        """Get a specific approval request."""
        row = get_approval_request(approval_id)
        return self._row_to_request(row) if row else None

    def check_expired(self, session_id: str) -> list[ApprovalRequest]:
        """Check for and mark expired approvals."""
        pending = self.get_pending(session_id)
        expired = []
        now = datetime.now()

        for req in pending:
            if req.expires_at and req.expires_at < now:
                # Mark as expired in database
                respond_to_approval(req.approval_id, "expired", "system")
                req.status = ApprovalStatus.EXPIRED
                expired.append(req)
                self.logger.warning("Approval %s expired", req.approval_id)

        return expired

    def auto_approve_low_risk(self, session_id: str) -> int:
        """
        Auto-approve low-risk requests.

        Returns:
            Number of approvals granted
        """
        pending = self.get_pending(session_id)
        approved = 0

        for req in pending:
            if self._is_low_risk(req):
                self.respond(req.approval_id, "approved", "auto_approval_system")
                approved += 1
                self.logger.info("Auto-approved low-risk request %s", req.approval_id)

        return approved

    def _is_low_risk(self, request: ApprovalRequest) -> bool:
        """Determine if a request is low risk."""
        # Low risk: read-only operations, cached data, non-mutating
        low_risk_types = {
            ApprovalType.DATA_ACCESS,
            ApprovalType.LITERATURE_SEARCH,
        }

        if request.request_type in low_risk_types:
            return True

        # Check parameters for mutating operations
        params = request.parameters
        if params.get("readonly", False):
            return True

        if params.get("method", "").upper() in ("GET", "HEAD", "OPTIONS"):
            return True

        return False

    def _row_to_request(self, row: dict[str, Any]) -> ApprovalRequest:
        """Convert database row to ApprovalRequest."""
        return ApprovalRequest(
            approval_id=row["approval_id"],
            session_id=row["session_id"],
            task_id=row["task_id"],
            request_type=ApprovalType(row["request_type"]),
            description=row["description"],
            parameters=row.get("parameters") if isinstance(row.get("parameters"), dict) else {},
            status=ApprovalStatus(row["status"]),
            requested_at=_to_datetime(row.get("requested_at")) or datetime.now(),
            expires_at=_to_datetime(row.get("expires_at")),
            responded_at=_to_datetime(row.get("responded_at")),
            responder_id=row.get("responder_id"),
            response=row.get("response"),
            metadata=row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
        )