"""GeneAI Multi-User Research Platform - Phase 5.5."""
from __future__ import annotations

from geneai.multi_user.core import (
    AuthManager,
    User,
    Team,
    TeamMember,
    Project,
    Session,
    Activity,
    Invitation,
    UserRole,
    TeamRole,
    ProjectVisibility,
    get_auth_manager,
)
from geneai.multi_user.ui import (
    render_multi_user_dashboard,
    render as render_multi_user,
)

__all__ = [
    # Core
    "AuthManager",
    "User",
    "Team",
    "TeamMember",
    "Project",
    "Session",
    "Activity",
    "Invitation",
    "UserRole",
    "TeamRole",
    "ProjectVisibility",
    "get_auth_manager",
    # UI
    "render_multi_user_dashboard",
    "render_multi_user",
]

__version__ = "5.5.0"