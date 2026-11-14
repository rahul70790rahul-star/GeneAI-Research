"""Streamlit UI for Multi-User Research Platform - Phase 5.5."""
from __future__ import annotations

import logging
import sqlite3

import streamlit as st
from datetime import datetime
from typing import Any

from geneai.multi_user.core import (
    AuthManager, User, Team, Project, Session,
    UserRole, TeamRole, ProjectVisibility,
    get_auth_manager
)

logger = logging.getLogger(__name__)


def render_multi_user_dashboard():
    """Render the multi-user platform dashboard."""
    st.title("👥 GeneAI Multi-User Research Platform")
    st.caption("Collaborative research with teams, projects, and access control")
    
    # Initialize auth manager
    if "auth_manager" not in st.session_state:
        st.session_state.auth_manager = get_auth_manager()
    
    auth: AuthManager = st.session_state.auth_manager
    
    # Check authentication
    if "user_session" not in st.session_state:
        render_login_page(auth)
        return
    
    session: Session = st.session_state.user_session
    user: User = auth.get_user(session.user_id)
    
    if not user or not user.is_active:
        st.session_state.pop("user_session", None)
        st.error("Session invalid. Please log in again.")
        st.rerun()
    
    # Sidebar with user info
    with st.sidebar:
        render_user_sidebar(user, auth)
        
        st.divider()
        
        # Navigation
        page = st.radio(
            "Navigation",
            ["Dashboard", "Teams", "Projects", "Activity", "Settings"],
            key="multi_user_nav"
        )
        
        st.divider()
        
        if st.button("🚪 Logout", use_container_width=True):
            auth.invalidate_session(session.session_id)
            st.session_state.pop("user_session", None)
            st.rerun()
    
    # Main content
    if page == "Dashboard":
        render_user_dashboard(user, auth)
    elif page == "Teams":
        render_teams_page(user, auth)
    elif page == "Projects":
        render_projects_page(user, auth)
    elif page == "Activity":
        render_activity_page(user, auth)
    elif page == "Settings":
        render_settings_page(user, auth)


def render_login_page(auth: AuthManager):
    """Render login page."""
    st.title("🔐 GeneAI Login")
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            remember = st.checkbox("Remember me (30 days)")
            submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
        
        if submitted:
            if not email or not password:
                st.error("Please enter email and password")
            else:
                expiry_hours = 720 if remember else 24  # 30 days or 24 hours
                session = auth.authenticate(email, password, expiry_hours=expiry_hours)
                user = auth.get_user(session.user_id) if session else None
                if session and user:
                    st.session_state.user_session = session
                    st.success(f"Welcome, {user.full_name or user.username}!")
                    st.rerun()
                else:
                    st.error("Invalid email or password")
    
    with tab2:
        with st.form("register_form"):
            username = st.text_input("Username")
            email = st.text_input("Email")
            full_name = st.text_input("Full Name")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Create Account", type="primary", use_container_width=True)
        
        if submitted:
            if not all([username, email, password]):
                st.error("Please fill all required fields")
            elif password != confirm_password:
                st.error("Passwords do not match")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters")
            else:
                try:
                    user_id = auth.create_user(username, email, password, full_name=full_name)
                    session = auth.create_session(user_id)
                    st.session_state.user_session = session
                    st.success("Account created successfully!")
                    st.rerun()
                except sqlite3.IntegrityError as e:
                    if "username" in str(e):
                        st.error("Username already taken")
                    elif "email" in str(e):
                        st.error("Email already registered")
                    else:
                        st.error("Registration failed")


def render_user_sidebar(user: User, auth: AuthManager):
    """Render user info in sidebar."""
    st.write(f"### {user.full_name or user.username}")
    st.caption(f"@{user.username} • {user.role.value.title()}")
    st.caption(user.email)
    
    # Quick stats
    teams = auth.list_user_teams(user.user_id)
    projects = auth.list_projects(user.user_id)
    
    col1, col2 = st.columns(2)
    col1.metric("Teams", len(teams))
    col2.metric("Projects", len(projects))


def render_user_dashboard(user: User, auth: AuthManager):
    """Render user dashboard."""
    st.subheader("📊 Dashboard")
    
    # Recent activity
    activities = auth.get_user_activities(user.user_id, 10)
    
    if activities:
        st.write("### Recent Activity")
        for activity in activities:
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{activity.action}** on {activity.resource_type}: `{activity.resource_id}`")
                    if activity.details:
                        st.json(activity.details, expanded=False)
                with col2:
                    st.caption(activity.timestamp[:19])
    else:
        st.info("No recent activity")
    
    # Quick actions
    st.divider()
    st.write("### Quick Actions")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("➕ Create Team", use_container_width=True):
            st.session_state.show_create_team = True
    
    with col2:
        if st.button("📁 Create Project", use_container_width=True):
            st.session_state.show_create_project = True
    
    with col3:
        if st.button("👥 Invite Member", use_container_width=True):
            st.session_state.show_invite = True
    
    with col4:
        if st.button("🔬 Start Analysis", use_container_width=True):
            st.info("Navigate to analysis modules from main menu")
    
    # Modals
    if st.session_state.get("show_create_team"):
        render_create_team_modal(user, auth)
    
    if st.session_state.get("show_create_project"):
        render_create_project_modal(user, auth)
    
    if st.session_state.get("show_invite"):
        render_invite_modal(user, auth)
    
    # My teams overview
    st.divider()
    st.write("### My Teams")
    teams = auth.list_user_teams(user.user_id)
    
    if teams:
        for team in teams:
            with st.expander(f"{'👑' if team.owner_id == user.user_id else '👤'} {team.name} ({len(team.members)} members)", expanded=False):
                st.write(f"**Description:** {team.description or 'No description'}")
                st.write(f"**Role:** {team.members.get(user.user_id, TeamRole.MEMBER).value}")
                st.write(f"**Members:** {', '.join(team.members.keys())}")
    else:
        st.info("You're not a member of any teams yet")


def render_create_team_modal(user: User, auth: AuthManager):
    """Render create team modal."""
    with st.form("create_team_form"):
        st.write("### Create New Team")
        name = st.text_input("Team Name")
        description = st.text_area("Description")
        submitted = st.form_submit_button("Create Team", type="primary")
        
        if submitted:
            if not name:
                st.error("Team name is required")
            else:
                team_id = auth.create_team(name, description, user.user_id)
                team = auth.get_team(team_id)
                st.success(f"Team '{team.name if team else name}' created!")
                st.session_state.show_create_team = False
                st.rerun()
        
        if st.form_submit_button("Cancel"):
            st.session_state.show_create_team = False
            st.rerun()


def render_create_project_modal(user: User, auth: AuthManager):
    """Render create project modal."""
    teams = auth.list_user_teams(user.user_id)
    
    with st.form("create_project_form"):
        st.write("### Create New Project")
        name = st.text_input("Project Name")
        description = st.text_area("Description")
        
        team_options = ["Personal"] + [f"{t.name} ({t.team_id})" for t in teams]
        selected_team = st.selectbox("Team (optional)", team_options)
        
        visibility = st.selectbox(
            "Visibility",
            [v.value for v in ProjectVisibility],
            format_func=lambda x: x.title()
        )
        
        submitted = st.form_submit_button("Create Project", type="primary")
        
        if submitted:
            if not name:
                st.error("Project name is required")
            else:
                team_id = None
                if selected_team != "Personal":
                    team_id = selected_team.split("(")[-1].rstrip(")")
                
                project_id = auth.create_project(
                    name, description, user.user_id,
                    team_id=team_id,
                    visibility=ProjectVisibility(visibility)
                )
                project = auth.get_project(project_id)
                st.success(f"Project '{project.name if project else name}' created!")
                st.session_state.show_create_project = False
                st.rerun()
        
        if st.form_submit_button("Cancel"):
            st.session_state.show_create_project = False
            st.rerun()


def render_invite_modal(user: User, auth: AuthManager):
    """Render invite member modal."""
    teams = auth.list_user_teams(user.user_id)
    owned_teams = [t for t in teams if t.owner_id == user.user_id]
    
    if not owned_teams:
        st.warning("You can only invite members to teams you own")
        if st.button("Close"):
            st.session_state.show_invite = False
            st.rerun()
        return
    
    with st.form("invite_form"):
        st.write("### Invite Team Member")
        email = st.text_input("Invitee Email")
        
        team_options = {f"{t.name} ({t.team_id})": t.team_id for t in owned_teams}
        selected_team = st.selectbox("Team", list(team_options.keys()))
        team_id = team_options[selected_team]
        
        role = st.selectbox(
            "Role",
            [r.value for r in TeamRole if r != TeamRole.OWNER],
            format_func=lambda x: x.title()
        )
        
        submitted = st.form_submit_button("Send Invitation", type="primary")
        
        if submitted:
            if not email:
                st.error("Email is required")
            else:
                invitation = auth.create_invitation(email, team_id=team_id, role=TeamRole(role), invited_by=user.user_id)
                st.success(f"Invitation sent to {email}!")
                st.info(f"Invitation token: {invitation.token}")
                st.session_state.show_invite = False
                st.rerun()
        
        if st.form_submit_button("Cancel"):
            st.session_state.show_invite = False
            st.rerun()


def render_teams_page(user: User, auth: AuthManager):
    """Render teams management page."""
    st.subheader("👥 Teams")
    
    tab1, tab2 = st.tabs(["My Teams", "Create Team"])
    
    with tab1:
        teams = auth.list_user_teams(user.user_id)
        
        if not teams:
            st.info("You're not a member of any teams")
            return
        
        for team in teams:
            is_owner = team.owner_id == user.user_id
            user_role = team.members.get(user.user_id, TeamRole.MEMBER)
            
            with st.expander(f"{'👑' if is_owner else '👤'} {team.name} — {user_role.value.title()}", expanded=True):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"**Description:** {team.description or 'No description'}")
                    st.write(f"**Created:** {team.created_at[:10]}")
                    st.write(f"**Members:** {len(team.members)}")
                
                with col2:
                    # Member list
                    st.write("**Members:**")
                    for member_id, role in team.members.items():
                        member = auth.get_user(member_id)
                        name = member.full_name or member.username if member else member_id
                        is_current = member_id == user.user_id
                        st.write(f"- {name} — {role.value} {'(You)' if is_current else ''}")
                    
                    # Actions
                    if is_owner:
                        if st.button("➕ Add Member", key=f"add_{team.team_id}"):
                            st.session_state[f"add_member_{team.team_id}"] = True
                    
                    if user_role in [TeamRole.OWNER, TeamRole.ADMIN] and not is_owner:
                        if st.button("🗑️ Leave Team", key=f"leave_{team.team_id}"):
                            auth.remove_team_member(team.team_id, user.user_id)
                            st.success("Left team")
                            st.rerun()
                
                # Add member form
                if st.session_state.get(f"add_member_{team.team_id}"):
                    with st.form(f"add_member_form_{team.team_id}"):
                        email = st.text_input("Email to invite")
                        role = st.selectbox("Role", [r.value for r in TeamRole if r != TeamRole.OWNER])
                        if st.form_submit_button("Invite"):
                            if email:
                                auth.create_invitation(email, team_id=team.team_id, role=TeamRole(role), invited_by=user.user_id)
                                st.success("Invitation sent!")
                                st.session_state[f"add_member_{team.team_id}"] = False
                                st.rerun()
    
    with tab2:
        with st.form("create_team_main"):
            st.write("### Create New Team")
            name = st.text_input("Team Name")
            description = st.text_area("Description")
            if st.form_submit_button("Create Team", type="primary"):
                if name:
                    team_id = auth.create_team(name, description, user.user_id)
                    team = auth.get_team(team_id)
                    st.success(f"Team '{team.name if team else name}' created!")
                    st.rerun()


def render_projects_page(user: User, auth: AuthManager):
    """Render projects management page."""
    st.subheader("📁 Projects")
    
    tab1, tab2 = st.tabs(["My Projects", "Create Project"])
    
    with tab1:
        projects = auth.list_projects(user.user_id)
        
        if not projects:
            st.info("No projects yet")
            return
        
        # Filter by team
        teams = auth.list_user_teams(user.user_id)
        team_filter = st.selectbox(
            "Filter by team",
            ["All"] + [f"{t.name} ({t.team_id})" for t in teams]
        )
        
        if team_filter != "All":
            team_id = team_filter.split("(")[-1].rstrip(")")
            projects = [p for p in projects if p.team_id == team_id]
        
        for project in projects:
            is_owner = project.owner_id == user.user_id
            visibility_icon = {
                ProjectVisibility.PRIVATE: "🔒",
                ProjectVisibility.TEAM: "👥",
                ProjectVisibility.PUBLIC: "🌐",
            }.get(project.visibility, "❓")
            
            with st.expander(f"{visibility_icon} {project.name}", expanded=True):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"**Description:** {project.description or 'No description'}")
                    st.write(f"**Visibility:** {project.visibility.value.title()}")
                    if project.team_id:
                        team = auth.get_team(project.team_id)
                        st.write(f"**Team:** {team.name if team else project.team_id}")
                    if project.tags:
                        st.write(f"**Tags:** {', '.join(project.tags)}")
                    st.write(f"**Created:** {project.created_at[:10]}")
                    st.write(f"**Updated:** {project.updated_at[:10]}")
                
                with col2:
                    if st.button("📝 Edit", key=f"edit_proj_{project.project_id}"):
                        st.session_state[f"edit_project_{project.project_id}"] = True
                    
                    if is_owner:
                        if st.button("🗑️ Delete", key=f"del_proj_{project.project_id}", type="secondary"):
                            if auth.delete_project(project.project_id, user.user_id):
                                st.success("Project deleted")
                                st.rerun()
                
                # Edit form
                if st.session_state.get(f"edit_project_{project.project_id}"):
                    with st.form(f"edit_proj_form_{project.project_id}"):
                        new_name = st.text_input("Name", project.name)
                        new_desc = st.text_area("Description", project.description)
                        new_visibility = st.selectbox(
                            "Visibility",
                            [v.value for v in ProjectVisibility],
                            index=[v.value for v in ProjectVisibility].index(project.visibility.value)
                        )
                        new_tags = st.text_input("Tags (comma-separated)", ", ".join(project.tags))
                        
                        if st.form_submit_button("Save"):
                            auth.update_project(
                                project.project_id,
                                name=new_name,
                                description=new_desc,
                                visibility=ProjectVisibility(new_visibility),
                                tags=[t.strip() for t in new_tags.split(",") if t.strip()]
                            )
                            st.success("Project updated!")
                            st.session_state[f"edit_project_{project.project_id}"] = False
                            st.rerun()
    
    with tab2:
        teams = auth.list_user_teams(user.user_id)
        
        with st.form("create_project_main"):
            st.write("### Create New Project")
            name = st.text_input("Project Name")
            description = st.text_area("Description")
            
            team_options = ["Personal"] + [f"{t.name} ({t.team_id})" for t in teams]
            selected_team = st.selectbox("Team (optional)", team_options)
            
            visibility = st.selectbox(
                "Visibility",
                [v.value for v in ProjectVisibility],
                format_func=lambda x: x.title()
            )
            
            tags = st.text_input("Tags (comma-separated)")
            
            if st.form_submit_button("Create Project", type="primary"):
                if name:
                    team_id = None
                    if selected_team != "Personal":
                        team_id = selected_team.split("(")[-1].rstrip(")")
                    
                    project_id = auth.create_project(
                        name, description, user.user_id,
                        team_id=team_id,
                        visibility=ProjectVisibility(visibility),
                        tags=[t.strip() for t in tags.split(",") if t.strip()]
                    )
                    project = auth.get_project(project_id)
                    st.success(f"Project '{project.name if project else name}' created!")
                    st.rerun()


def render_activity_page(user: User, auth: AuthManager):
    """Render activity page."""
    st.subheader("📋 Activity Log")
    
    activities = auth.get_user_activities(user.user_id, 100)
    
    if not activities:
        st.info("No activity recorded")
        return
    
    # Filter
    action_filter = st.selectbox(
        "Filter by action",
        ["All"] + sorted(set(a.action for a in activities))
    )
    
    if action_filter != "All":
        activities = [a for a in activities if a.action == action_filter]
    
    # Display
    for activity in activities:
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{activity.action}** on {activity.resource_type}: `{activity.resource_id}`")
                if activity.details:
                    with st.expander("Details"):
                        st.json(activity.details)
            with col2:
                st.caption(activity.timestamp[:19])
                st.caption(f"IP: {activity.ip_address or 'N/A'}")


def render_settings_page(user: User, auth: AuthManager):
    """Render user settings page."""
    st.subheader("⚙️ Settings")
    
    tab1, tab2, tab3 = st.tabs(["Profile", "Security", "Preferences"])
    
    with tab1:
        with st.form("profile_form"):
            st.write("### Profile")
            full_name = st.text_input("Full Name", user.full_name)
            username = st.text_input("Username", user.username, disabled=True)
            email = st.text_input("Email", user.email, disabled=True)
            avatar_url = st.text_input("Avatar URL", user.avatar_url)
            
            if st.form_submit_button("Save Profile"):
                auth.update_user(user.user_id, full_name=full_name, avatar_url=avatar_url)
                st.success("Profile updated!")
                st.rerun()
    
    with tab2:
        with st.form("password_form"):
            st.write("### Change Password")
            old_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            if st.form_submit_button("Change Password"):
                if new_password != confirm_password:
                    st.error("Passwords do not match")
                elif len(new_password) < 8:
                    st.error("Password must be at least 8 characters")
                else:
                    if auth.change_password(user.user_id, old_password, new_password):
                        st.success("Password changed!")
                        # Invalidate other sessions
                        auth.invalidate_user_sessions(user.user_id)
                        st.info("Other sessions logged out for security")
                    else:
                        st.error("Current password is incorrect")
        
        st.divider()
        
        with st.form("sessions_form"):
            st.write("### Active Sessions")
            st.info("Session management would show active sessions here")
            if st.form_submit_button("Log out of all other sessions"):
                auth.invalidate_user_sessions(user.user_id)
                st.success("All other sessions invalidated")
    
    with tab3:
        with st.form("preferences_form"):
            st.write("### Preferences")
            prefs = user.preferences
            
            theme = st.selectbox("Theme", ["light", "dark", "auto"], 
                               index=["light", "dark", "auto"].index(prefs.get("theme", "auto")))
            default_project = st.text_input("Default Project", prefs.get("default_project", ""))
            notifications = st.checkbox("Email Notifications", prefs.get("notifications", True))
            auto_save = st.checkbox("Auto-save Analysis", prefs.get("auto_save", True))
            
            if st.form_submit_button("Save Preferences"):
                auth.update_user(user.user_id, preferences={
                    "theme": theme,
                    "default_project": default_project,
                    "notifications": notifications,
                    "auto_save": auto_save,
                })
                st.success("Preferences saved!")
                st.rerun()


def render_admin_panel(auth: AuthManager):
    """Render admin panel (for admin users)."""
    st.subheader("🛠️ Admin Panel")
    
    users = auth.list_users()
    
    st.write(f"### User Management ({len(users)} users)")
    
    for u in users:
        with st.expander(f"{u.username} ({u.email}) — {u.role.value}", expanded=False):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.write(f"**Full Name:** {u.full_name}")
                st.write(f"**Role:** {u.role.value}")
                st.write(f"**Active:** {'Yes' if u.is_active else 'No'}")
                st.write(f"**Created:** {u.created_at[:10]}")
                st.write(f"**Last Login:** {u.last_login[:19] if u.last_login else 'Never'}")
            
            with col2:
                new_role = st.selectbox(
                    "Role",
                    [r.value for r in UserRole],
                    index=[r.value for r in UserRole].index(u.role.value),
                    key=f"role_{u.user_id}"
                )
                
                if st.button("Update Role", key=f"update_role_{u.user_id}"):
                    auth.update_user(u.user_id, role=UserRole(new_role))
                    st.success("Role updated")
                    st.rerun()
                
                if u.is_active:
                    if st.button("Deactivate", key=f"deactivate_{u.user_id}", type="secondary"):
                        auth.update_user(u.user_id, is_active=False)
                        auth.invalidate_user_sessions(u.user_id)
                        st.success("User deactivated")
                        st.rerun()
                else:
                    if st.button("Activate", key=f"activate_{u.user_id}"):
                        auth.update_user(u.user_id, is_active=True)
                        st.success("User activated")
                        st.rerun()


def render():
    """Main render function."""
    # Check if user is admin
    if "user_session" in st.session_state:
        auth = get_auth_manager()
        session = st.session_state.user_session
        user = auth.get_user(session.user_id)
        
        if user and user.role == UserRole.ADMIN:
            # Show admin panel in sidebar
            with st.sidebar:
                if st.checkbox("Show Admin Panel"):
                    render_admin_panel(auth)
    
    render_multi_user_dashboard()


if __name__ == "__main__":
    render()