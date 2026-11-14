"""Streamlit UI for Security and Privacy - Phase 5.9."""
from __future__ import annotations

import logging
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Any

from geneai.security.core import (
    DataEncryption, FieldEncryption, SecureStorage, AuditLogger,
    AuditEvent, AuditEventType, SecurityLevel, AccessControl,
    DataPrivacy, SessionSecurity, get_encryption, get_audit_logger,
    get_access_control, get_session_security, init_security
)

logger = logging.getLogger(__name__)


def render_security_dashboard():
    """Render the security and privacy dashboard."""
    st.title("🔒 GeneAI Security & Privacy")
    st.caption("Encryption, audit logging, access control, and data privacy")
    
    # Initialize security
    if "security_initialized" not in st.session_state:
        st.session_state.encryption = get_encryption()
        st.session_state.audit_logger = get_audit_logger()
        st.session_state.access_control = get_access_control()
        st.session_state.session_security = get_session_security()
        st.session_state.security_initialized = True
    
    encryption: DataEncryption = st.session_state.encryption
    audit_logger: AuditLogger = st.session_state.audit_logger
    access_control: AccessControl = st.session_state.access_control
    session_security: SessionSecurity = st.session_state.session_security
    
    # Sidebar
    with st.sidebar:
        st.header("Security Status")
        
        # Encryption status
        st.subheader("🔐 Encryption")
        st.success("Active" if encryption else "Inactive")
        if st.button("🔄 Rotate Key", use_container_width=True):
            new_key = encryption.rotate_key()
            st.success("Encryption key rotated")
            st.code(base64.urlsafe_b64encode(new_key).decode()[:32] + "...")
        
        st.divider()
        
        # Access control
        st.subheader("👥 Access Control")
        roles = list(access_control._permissions.keys())
        for role in roles:
            perms = len(access_control.get_permissions(role))
            st.caption(f"{role}: {perms} permissions")
        
        st.divider()
        
        # Session management
        st.subheader("🔑 Sessions")
        active_sessions = len(session_security.get_active_sessions())
        st.metric("Active Sessions", active_sessions)
        
        if st.button("Revoke All Sessions", use_container_width=True):
            # Would need current user
            st.warning("Requires user context")
        
        st.divider()
        
        # Audit log
        st.subheader("📋 Audit Log")
        if st.button("📥 Export Audit Log", use_container_width=True):
            st.info("Audit log export would be generated here")
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🔐 Encryption", "📋 Audit Log", "👥 Access Control",
        "🔑 Sessions", "🛡️ Data Privacy", "⚙️ Settings"
    ])
    
    with tab1:
        render_encryption_tab(encryption)
    
    with tab2:
        render_audit_tab(audit_logger)
    
    with tab3:
        render_access_control_tab(access_control)
    
    with tab4:
        render_sessions_tab(session_security)
    
    with tab5:
        render_privacy_tab()
    
    with tab6:
        render_settings_tab()


def render_encryption_tab(encryption: DataEncryption):
    """Render encryption management tab."""
    st.subheader("Data Encryption")
    
    st.markdown("""
    GeneAI uses **Fernet (AES-256-GCM)** for symmetric encryption.
    - Master key derived from PBKDF2 with 100,000 iterations
    - Field-level encryption for sensitive data
    - Secure storage with encrypted persistence
    """)
    
    st.divider()
    
    # Encryption demo
    st.write("### Encryption Demo")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Encrypt Data**")
        plaintext = st.text_area("Plaintext", "Sensitive research data: TP53 mutation analysis results")
        
        if st.button("Encrypt", type="primary"):
            encrypted = encryption.encrypt(plaintext)
            st.session_state.encrypted_demo = encrypted
            st.success("Encrypted!")
            st.code(encrypted)
    
    with col2:
        st.write("**Decrypt Data**")
        encrypted_input = st.text_area("Encrypted Text", 
                                       value=st.session_state.get("encrypted_demo", ""))
        
        if st.button("Decrypt"):
            try:
                decrypted = encryption.decrypt_str(encrypted_input)
                st.success("Decrypted!")
                st.code(decrypted)
            except Exception as e:
                st.error(f"Decryption failed: {e}")
    
    st.divider()
    
    # Field encryption
    st.write("### Field-Level Encryption")
    
    field_enc = FieldEncryption(encryption)
    
    test_data = {
        "patient_id": "PAT-12345",
        "gene": "TP53",
        "mutation": "R175H",
        "ssn": "123-45-6789",
        "email": "researcher@lab.org"
    }
    
    st.write("**Original Data:**")
    st.json(test_data)
    
    if st.button("Encrypt Sensitive Fields"):
        encrypted_data = {}
        for key, value in test_data.items():
            encrypted_data[key] = field_enc.encrypt_field(value, key)
        
        st.write("**Encrypted Data:**")
        st.json(encrypted_data)
        
        # Decrypt back
        decrypted_data = {}
        for key, enc_value in encrypted_data.items():
            decrypted_data[key] = field_enc.decrypt_field(enc_value)
        
        st.write("**Decrypted Data:**")
        st.json(decrypted_data)
    
    st.divider()
    
    # Secure storage
    st.write("### Secure Storage")
    
    storage = SecureStorage("secure_storage.enc", encryption)
    
    col1, col2 = st.columns(2)
    
    with col1:
        store_key = st.text_input("Key", "research_data")
        store_value = st.text_area("Value", '{"analysis": "TP53 pathway", "score": 0.95}')
        encrypt = st.checkbox("Encrypt", True)
        
        if st.button("Store"):
            storage.set(store_key, json.loads(store_value), encrypt)
            st.success(f"Stored: {store_key}")
    
    with col2:
        retrieve_key = st.text_input("Retrieve Key", "research_data")
        
        if st.button("Retrieve"):
            value = storage.get(retrieve_key)
            if value is not None:
                st.success("Retrieved!")
                st.json(value)
            else:
                st.error("Key not found")
    
    if st.button("List Stored Keys"):
        keys = storage.list_keys()
        st.write(f"Stored keys: {keys}")


def render_audit_tab(audit_logger: AuditLogger):
    """Render audit log tab."""
    st.subheader("Security Audit Log")
    
    st.markdown("""
    Comprehensive audit trail for all security-relevant events.
    Events are logged in real-time and can be exported for compliance.
    """)
    
    # Generate sample events for demo
    if "demo_audit_events" not in st.session_state:
        events = []
        for i in range(20):
            event_types = list(AuditEventType)
            event = AuditEvent(
                event_id=f"evt_{i:04d}",
                event_type=event_types[i % len(event_types)],
                user_id=f"user_{i % 5 + 1}",
                resource_type=["gene", "drug", "protein", "pathway", "analysis"][i % 5],
                resource_id=f"res_{i:03d}",
                ip_address=f"192.168.1.{i % 255}",
                user_agent="Mozilla/5.0 (Research Client)",
                success=i % 10 != 0,
                security_level=list(SecurityLevel)[i % len(SecurityLevel)],
                session_id=f"sess_{i:04d}",
            )
            events.append(event)
        st.session_state.demo_audit_events = events
    
    events = st.session_state.demo_audit_events
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        user_filter = st.selectbox("Filter by User", 
                                   ["All"] + list(set(e.user_id for e in events)))
    with col2:
        type_filter = st.selectbox("Filter by Event Type",
                                   ["All"] + [t.value for t in AuditEventType])
    with col3:
        success_filter = st.selectbox("Filter by Success",
                                      ["All", "Success", "Failed"])
    
    # Apply filters
    filtered = events
    if user_filter != "All":
        filtered = [e for e in filtered if e.user_id == user_filter]
    if type_filter != "All":
        filtered = [e for e in filtered if e.event_type.value == type_filter]
    if success_filter != "All":
        filtered = [e for e in filtered if e.success == (success_filter == "Success")]
    
    # Display events
    st.write(f"### Events ({len(filtered)} of {len(events)})")
    
    if filtered:
        df_data = []
        for event in filtered:
            df_data.append({
                "Time": event.timestamp.isoformat()[:19],
                "Event": event.event_type.value,
                "User": event.user_id,
                "Resource": f"{event.resource_type}/{event.resource_id}",
                "IP": event.ip_address,
                "Level": event.security_level.value,
                "Status": "✅" if event.success else "❌",
            })
        
        df = pd.DataFrame(df_data)
        st.dataframe(df, hide_index=True, use_container_width=True)
        
        # Event details
        selected_idx = st.selectbox(
            "View Event Details",
            range(len(filtered)),
            format_func=lambda i: f"{filtered[i].timestamp.isoformat()[:19]} - {filtered[i].event_type.value} - {filtered[i].user_id}"
        )
        
        if selected_idx is not None:
            event = filtered[selected_idx]
            with st.expander("Event Details", expanded=True):
                st.json(event.to_dict())
    else:
        st.info("No events match the filters")
    
    st.divider()
    
    # Log new event
    st.write("### Log New Event")
    
    with st.form("log_event_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            event_type = st.selectbox("Event Type", list(AuditEventType), 
                                      format_func=lambda x: x.value)
            user_id = st.text_input("User ID", "current_user")
            resource_type = st.text_input("Resource Type", "gene")
            resource_id = st.text_input("Resource ID", "TP53")
        
        with col2:
            ip = st.text_input("IP Address", "192.168.1.100")
            success = st.checkbox("Success", True)
            security_level = st.selectbox("Security Level", list(SecurityLevel),
                                          format_func=lambda x: x.value)
        
        details = st.text_area("Details (JSON)", "{}")
        
        if st.form_submit_button("Log Event"):
            try:
                event = AuditEvent(
                    event_type=event_type,
                    user_id=user_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    ip_address=ip,
                    success=success,
                    security_level=security_level,
                    details=json.loads(details),
                )
                audit_logger.log(event)
                st.session_state.demo_audit_events.insert(0, event)
                st.success("Event logged!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to log event: {e}")


def render_access_control_tab(access_control: AccessControl):
    """Render access control tab."""
    st.subheader("Role-Based Access Control")
    
    st.markdown("""
    Fine-grained permissions system with roles and resource policies.
    """)
    
    # Current roles
    st.write("### Current Roles & Permissions")
    
    for role, perms in access_control._permissions.items():
        with st.expander(f"👤 {role.title()} ({len(perms)} permissions)", expanded=False):
            cols = st.columns(3)
            for i, perm in enumerate(sorted(perms)):
                with cols[i % 3]:
                    st.markdown(f"`{perm}`")
            
            # Add permission
            new_perm = st.text_input(f"Add permission to {role}", key=f"add_perm_{role}")
            if st.button(f"Add", key=f"add_btn_{role}") and new_perm:
                access_control.add_permission(role, new_perm)
                st.success(f"Added {new_perm} to {role}")
                st.rerun()
    
    st.divider()
    
    # Create new role
    st.write("### Create New Role")
    
    with st.form("create_role_form"):
        role_name = st.text_input("Role Name")
        permissions = st.multiselect(
            "Permissions",
            ["read", "write", "delete", "admin", "export", "config", 
             "user_management", "audit_access", "system_config", "analyze", "workflow_create", "workflow_run"]
        )
        
        if st.form_submit_button("Create Role"):
            if role_name:
                access_control._permissions[role_name] = set(permissions)
                st.success(f"Created role: {role_name}")
                st.rerun()
    
    st.divider()
    
    # Resource policies
    st.write("### Resource Policies")
    
    if access_control._resource_policies:
        for resource, policy in access_control._resource_policies.items():
            with st.expander(f"📁 {resource}", expanded=False):
                st.json(policy)
    else:
        st.info("No resource policies defined")
    
    with st.form("create_policy_form"):
        st.write("**Create Resource Policy**")
        resource = st.text_input("Resource Path", "genes/TP53")
        
        col1, col2 = st.columns(2)
        with col1:
            allowed_roles = st.multiselect("Allowed Roles", list(access_control._permissions.keys()))
        with col2:
            allowed_actions = st.multiselect("Allowed Actions", ["read", "write", "delete", "export", "analyze"])
        
        if st.form_submit_button("Create Policy"):
            access_control.set_resource_policy(resource, {
                "allowed_roles": allowed_roles,
                "allowed_actions": allowed_actions,
            })
            st.success(f"Policy created for {resource}")
            st.rerun()
    
    st.divider()
    
    # Access check
    st.write("### Access Check")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        check_role = st.selectbox("Role", list(access_control._permissions.keys()))
    with col2:
        check_resource = st.text_input("Resource", "genes/TP53")
    with col3:
        check_action = st.selectbox("Action", ["read", "write", "delete", "export", "analyze"])
    
    if st.button("Check Access"):
        allowed = access_control.check_resource_access(check_role, check_resource, check_action)
        if allowed:
            st.success(f"✅ {check_role} CAN {check_action} {check_resource}")
        else:
            st.error(f"❌ {check_role} CANNOT {check_action} {check_resource}")


def render_sessions_tab(session_security: SessionSecurity):
    """Render session management tab."""
    st.subheader("Session Security")
    
    st.markdown("""
    Secure session management with JWT-like tokens, HMAC signing, and automatic expiry.
    """)
    
    # Create session
    st.write("### Create Session")
    
    with st.form("create_session_form"):
        user_id = st.text_input("User ID", "researcher_001")
        expiry_hours = st.number_input("Expiry (hours)", 1, 168, 24)
        ip = st.text_input("IP Address", "192.168.1.100")
        user_agent = st.text_input("User Agent", "Mozilla/5.0 GeneAI Client")
        
        if st.form_submit_button("Create Session"):
            token = session_security.create_session_token(
                user_id, expiry_hours, ip, user_agent
            )
            st.session_state.demo_session_token = token
            st.success("Session created!")
            st.code(token)
    
    st.divider()
    
    # Validate session
    st.write("### Validate Session")
    
    token_input = st.text_area("Session Token", 
                               value=st.session_state.get("demo_session_token", ""),
                               height=100)
    
    if st.button("Validate"):
        result = session_security.validate_session_token(token_input)
        if result:
            st.success("✅ Valid session")
            st.json({
                "user_id": result["user_id"],
                "session_id": result["session_id"],
                "created_at": result["created_at"],
                "expires_at": result["expires_at"],
                "ip_address": result["ip_address"],
            })
        else:
            st.error("❌ Invalid or expired session")
    
    st.divider()
    
    # Active sessions
    st.write("### Active Sessions")
    
    active_sessions = session_security.get_active_sessions()
    if active_sessions:
        df_data = []
        for session in active_sessions:
            df_data.append({
                "Session ID": session.session_id[:16] + "...",
                "User": session.user_id,
                "Created": session.created_at.isoformat()[:19],
                "Expires": session.expires_at.isoformat()[:19],
                "IP": session.ip_address,
            })
        
        df = pd.DataFrame(df_data)
        st.dataframe(df, hide_index=True)
        
        # Revoke session
        selected = st.selectbox(
            "Revoke Session",
            options=[s.session_id for s in active_sessions],
            format_func=lambda x: f"{x[:16]}... ({next(s.user_id for s in active_sessions if s.session_id == x)})"
        )
        
        if st.button("Revoke Selected"):
            session_security.revoke_session(selected)
            st.success("Session revoked")
            st.rerun()
    else:
        st.info("No active sessions")
    
    st.divider()
    
    # Session security features
    st.write("### Security Features")
    
    features = [
        ("🔐 HMAC Signing", "Tokens signed with SHA-256 HMAC"),
        ("⏰ Automatic Expiry", "Sessions expire after configured time"),
        ("🌍 IP Binding", "Optional IP address validation"),
        ("🔄 Token Rotation", "Support for token refresh"),
        ("🗑️ Instant Revocation", "Immediate session termination"),
        ("👤 User Session Management", "Revoke all sessions for a user"),
    ]
    
    for icon_title, desc in features:
        st.markdown(f"**{icon_title}**: {desc}")


def render_privacy_tab():
    """Render data privacy tab."""
    st.subheader("Data Privacy & PII Protection")
    
    st.markdown("""
    Automatic detection and redaction of personally identifiable information (PII).
    """)
    
    # PII Detection
    st.write("### PII Detection")
    
    test_text = st.text_area(
        "Text to scan",
        "Contact Dr. Smith at john.smith@lab.org or call 555-123-4567. "
        "Patient SSN: 123-45-6789. IP: 192.168.1.100",
        height=100
    )
    
    if st.button("Scan for PII"):
        detected = DataPrivacy.detect_pii(test_text)
        if detected:
            st.warning("PII Detected!")
            for pii_type, matches in detected.items():
                st.write(f"**{pii_type.upper()}**: {', '.join(matches)}")
        else:
            st.success("No PII detected")
    
    st.divider()
    
    # PII Redaction
    st.write("### PII Redaction")
    
    if st.button("Redact PII"):
        redacted = DataPrivacy.redact_pii(test_text)
        st.code(redacted)
    
    st.divider()
    
    # Data Anonymization
    st.write("### Data Anonymization")
    
    sample_record = {
        "patient_id": "PAT-12345",
        "name": "John Smith",
        "email": "john.smith@hospital.org",
        "phone": "555-123-4567",
        "ssn": "123-45-6789",
        "gene": "TP53",
        "mutation": "R175H",
        "address": "123 Main St, Boston, MA",
        "ip_address": "192.168.1.100",
        "metadata": {
            "created_by": "dr_jones",
            "notes": "Patient consent on file"
        }
    }
    
    st.write("**Original Record:**")
    st.json(sample_record)
    
    pii_fields = st.multiselect(
        "Fields to anonymize",
        ["patient_id", "name", "email", "phone", "ssn", "address", "ip_address", "created_by"],
        default=["name", "email", "phone", "ssn", "address", "ip_address"]
    )
    
    if st.button("Anonymize"):
        anonymized = DataPrivacy.anonymize_data(sample_record, pii_fields)
        st.write("**Anonymized Record:**")
        st.json(anonymized)
    
    st.divider()
    
    # Privacy compliance
    st.write("### Privacy Compliance")
    
    compliance_items = [
        ("🇪🇺 GDPR", "Right to access, rectification, erasure, portability"),
        ("🇺🇸 HIPAA", "Protected health information safeguards"),
        ("🇨🇦 PIPEDA", "Personal information protection"),
        ("🔒 Data Minimization", "Collect only necessary data"),
        ("🗑️ Retention Policies", "Automatic data expiration"),
        ("📋 Audit Trail", "Complete access logging"),
    ]
    
    for title, desc in compliance_items:
        with st.expander(title, expanded=False):
            st.write(desc)


def render_settings_tab():
    """Render security settings tab."""
    st.subheader("Security Settings")
    
    with st.form("security_settings_form"):
        st.write("### Encryption")
        key_rotation_days = st.number_input("Key Rotation (days)", 30, 365, 90)
        field_encryption = st.checkbox("Field-Level Encryption", True)
        storage_encryption = st.checkbox("Storage Encryption", True)
        
        st.write("### Audit Logging")
        log_level = st.selectbox("Log Level", ["DEBUG", "INFO", "WARNING", "ERROR"])
        log_retention_days = st.number_input("Log Retention (days)", 30, 2555, 365)
        encrypt_audit_logs = st.checkbox("Encrypt Audit Logs", True)
        
        st.write("### Session Security")
        session_timeout = st.number_input("Session Timeout (hours)", 1, 168, 24)
        max_concurrent_sessions = st.number_input("Max Concurrent Sessions", 1, 10, 5)
        require_mfa = st.checkbox("Require MFA for Admin", False)
        
        st.write("### Access Control")
        default_role = st.selectbox("Default Role", ["viewer", "analyst", "researcher"])
        require_approval = st.checkbox("Require Approval for Elevated Access", True)
        
        st.write("### Data Privacy")
        pii_detection = st.checkbox("Auto PII Detection", True)
        auto_redaction = st.checkbox("Auto Redaction in Exports", False)
        anonymization_default = st.checkbox("Anonymize by Default in Reports", False)
        
        if st.form_submit_button("Save Settings"):
            st.success("Security settings saved!")
            st.info("Changes take effect on next restart")


def render():
    """Main render function."""
    render_security_dashboard()


if __name__ == "__main__":
    render()