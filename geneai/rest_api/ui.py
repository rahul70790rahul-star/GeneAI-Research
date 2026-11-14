"""Streamlit UI for REST API - Phase 5.7."""
from __future__ import annotations

import json
import logging
import secrets
import requests
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Any

from geneai.rest_api.core import (
    GeneAIAPI, APIKey, APIResponse, get_api, create_api
)

logger = logging.getLogger(__name__)


def render_rest_api_dashboard():
    """Render the REST API dashboard."""
    st.title("🔌 GeneAI REST API")
    st.caption("Programmatic access to all GeneAI research capabilities")
    
    # Initialize API
    if "rest_api" not in st.session_state:
        st.session_state.rest_api = get_api()
    
    api: GeneAIAPI = st.session_state.rest_api
    
    # Sidebar
    with st.sidebar:
        st.header("API Server")
        
        # Server status
        st.subheader("Status")
        st.success("🟢 Running" if st.session_state.get("api_server_running") else "🔴 Stopped")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ Start", use_container_width=True, disabled=st.session_state.get("api_server_running")):
                st.session_state.api_server_running = True
                st.info("API server would start in background")
                st.rerun()
        with col2:
            if st.button("⏹️ Stop", use_container_width=True, disabled=not st.session_state.get("api_server_running")):
                st.session_state.api_server_running = False
                st.info("API server stopped")
                st.rerun()
        
        st.divider()
        
        # Configuration
        st.subheader("Configuration")
        host = st.text_input("Host", "0.0.0.0")
        port = st.number_input("Port", 1000, 65535, 5000)
        debug = st.checkbox("Debug Mode")
        
        st.divider()
        
        # API Keys
        st.subheader("API Keys")
        keys = list(api.api_keys.values())
        active_keys = [k for k in keys if k.is_active]
        
        st.metric("Active Keys", len(active_keys))
        st.metric("Total Keys", len(keys))
        
        if st.button("🔑 Create Demo Key", use_container_width=True):
            # Demo key already created in init
            st.info("Demo key: geneai_demo_key_12345")
        
        st.divider()
        
        # Quick test
        st.subheader("Quick Test")
        test_endpoint = st.selectbox(
            "Endpoint",
            ["/health", "/api/v1/info", "/api/v1/genes/search?q=TP53"]
        )
        
        if st.button("Test Endpoint", use_container_width=True):
            st.code(f"curl -H 'Authorization: Bearer geneai_demo_key_12345' http://localhost:{port}{test_endpoint}")
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📚 Documentation", "🔑 API Keys", "🧪 Test Console", 
        "📊 Analytics", "⚙️ Settings"
    ])
    
    with tab1:
        render_docs_tab()
    
    with tab2:
        render_keys_tab(api)
    
    with tab3:
        render_test_console_tab(api)
    
    with tab4:
        render_analytics_tab(api)
    
    with tab5:
        render_settings_tab()


def render_docs_tab():
    """Render API documentation."""
    st.subheader("API Documentation")
    
    st.markdown("""
    ### Base URL
    ```
    http://localhost:5000/api/v1
    ```
    
    ### Authentication
    All endpoints (except `/health` and `/api/v1/info`) require an API key:
    ```bash
    curl -H "Authorization: Bearer YOUR_API_KEY" http://localhost:5000/api/v1/endpoint
    ```
    
    ### Rate Limits
    - Default: 1000 requests/hour per key
    - Analysis endpoints: 10-50 requests/minute
    - Search endpoints: 200 requests/minute
    
    ### Response Format
    All responses follow a standard format:
    ```json
    {
      "success": true,
      "data": {...},
      "error": null,
      "error_code": null,
      "meta": {}
    }
    ```
    """)
    
    # Endpoints documentation
    st.subheader("Endpoints")
    
    endpoints = [
        {
            "category": "Sequence Analysis",
            "endpoints": [
                ("POST", "/sequence/analyze", "Analyze DNA/RNA/protein sequence"),
                ("POST", "/sequence/parse", "Parse FASTA/FASTQ file"),
            ]
        },
        {
            "category": "Variant Analysis",
            "endpoints": [
                ("POST", "/variants/parse", "Parse VCF file"),
            ]
        },
        {
            "category": "Gene Analysis",
            "endpoints": [
                ("GET", "/genes/search?q=QUERY", "Search genes"),
                ("GET", "/genes/{symbol}", "Get gene with related data"),
            ]
        },
        {
            "category": "Disease Analysis",
            "endpoints": [
                ("GET", "/diseases/search?q=QUERY", "Search diseases"),
                ("GET", "/diseases/{name}/genes", "Get disease-associated genes"),
                ("GET", "/diseases/{name}/drugs", "Get drugs for disease"),
            ]
        },
        {
            "category": "Drug Discovery",
            "endpoints": [
                ("GET", "/drugs/search?q=QUERY", "Search drugs"),
                ("GET", "/drugs/{id}", "Get drug with targets"),
            ]
        },
        {
            "category": "Protein Analysis",
            "endpoints": [
                ("GET", "/proteins/search?q=QUERY", "Search proteins"),
                ("GET", "/proteins/{uniprot_id}", "Get protein with interactions"),
            ]
        },
        {
            "category": "Pathways",
            "endpoints": [
                ("GET", "/pathways/search?q=QUERY", "Search pathways"),
            ]
        },
        {
            "category": "Literature",
            "endpoints": [
                ("GET", "/literature/search?q=QUERY", "Search publications"),
            ]
        },
        {
            "category": "Analysis",
            "endpoints": [
                ("POST", "/analysis/admet", "Predict ADMET properties"),
                ("POST", "/analysis/drug-target", "Predict drug-target binding"),
                ("POST", "/analysis/repurposing", "Find repurposing candidates"),
                ("POST", "/analysis/biomarker", "Discover biomarkers"),
            ]
        },
        {
            "category": "Workflows",
            "endpoints": [
                ("POST", "/workflows/precision", "Run precision drug discovery"),
                ("POST", "/workflows/mutation-to-drug", "Run mutation-to-drug workflow"),
            ]
        },
        {
            "category": "Knowledge Graph",
            "endpoints": [
                ("POST", "/knowledge/query", "Query knowledge graph"),
            ]
        },
        {
            "category": "AI Assistant",
            "endpoints": [
                ("POST", "/assistant/ask", "Ask research question"),
            ]
        },
        {
            "category": "Automation",
            "endpoints": [
                ("GET", "/automation/tasks", "List automation tasks"),
                ("POST", "/automation/tasks", "Create automation task"),
                ("POST", "/automation/tasks/{id}/run", "Run automation task"),
            ]
        },
    ]
    
    for cat in endpoints:
        with st.expander(f"📁 {cat['category']}", expanded=False):
            for method, path, desc in cat['endpoints']:
                st.markdown(f"`{method} {path}` - {desc}")


def render_keys_tab(api: GeneAIAPI):
    """Render API keys management."""
    st.subheader("API Key Management")
    
    # Create new key
    with st.expander("➕ Create New Key", expanded=True):
        with st.form("create_key_form"):
            name = st.text_input("Key Name", "My Research Key")
            scopes = st.multiselect(
                "Scopes",
                ["read", "write", "analyze", "admin"],
                default=["read", "analyze"]
            )
            rate_limit = st.number_input("Rate Limit (req/hour)", 100, 100000, 1000)
            expires_days = st.number_input("Expires in Days (0 = never)", 0, 365, 0)
            
            if st.form_submit_button("Create Key", type="primary"):
                import hashlib
                key_id = secrets.token_urlsafe(16)
                raw_key = f"geneai_{secrets.token_urlsafe(32)}"
                key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
                
                expires_at = None
                if expires_days > 0:
                    expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
                
                new_key = APIKey(
                    key_id=key_id,
                    key_hash=key_hash,
                    name=name,
                    user_id="current_user",
                    scopes=scopes,
                    rate_limit=rate_limit,
                    expires_at=expires_at,
                )
                api.api_keys[key_id] = new_key
                
                st.success("Key created!")
                st.code(f"Key ID: {key_id}")
                st.code(f"API Key: {raw_key}")
                st.warning("⚠️ Save this key now! It will not be shown again.")
    
    st.divider()
    
    # List keys
    st.subheader("Existing Keys")
    
    keys = [k for k in api.api_keys.values() if k.is_active]
    
    if not keys:
        st.info("No active keys")
    else:
        for key in keys:
            with st.expander(f"🔑 {key.name} ({key.key_id[:12]}...)", expanded=False):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write(f"**Key ID:** {key.key_id}")
                    st.write(f"**Scopes:** {', '.join(key.scopes)}")
                    st.write(f"**Rate Limit:** {key.rate_limit}/hour")
                    st.write(f"**Created:** {key.created_at[:19]}")
                    if key.expires_at:
                        st.write(f"**Expires:** {key.expires_at[:10]}")
                    if key.last_used:
                        st.write(f"**Last Used:** {key.last_used[:19]}")
                
                with col2:
                    if st.button("🗑️ Revoke", key=f"revoke_{key.key_id}", use_container_width=True):
                        key.is_active = False
                        st.success("Key revoked")
                        st.rerun()


def render_test_console_tab(api: GeneAIAPI):
    """Render API test console."""
    st.subheader("API Test Console")
    st.write("Test API endpoints directly from the browser")
    
    # API server URL
    api_base_url = st.text_input("API Base URL", "http://localhost:5000", help="Base URL of the running API server")
    
    # Select endpoint
    endpoints = [
        ("GET", "/health", "Health check"),
        ("GET", "/api/v1/info", "API info"),
        ("GET", "/api/v1/genes/search?q=TP53", "Search genes"),
        ("GET", "/api/v1/diseases/search?q=breast cancer", "Search diseases"),
        ("GET", "/api/v1/drugs/search?q=aspirin", "Search drugs"),
        ("GET", "/api/v1/proteins/search?q=P53", "Search proteins"),
        ("GET", "/api/v1/pathways/search?q=apoptosis", "Search pathways"),
        ("POST", "/api/v1/sequence/analyze", "Analyze sequence"),
        ("POST", "/api/v1/analysis/admet", "Predict ADMET"),
        ("POST", "/api/v1/assistant/ask", "Ask assistant"),
    ]
    
    selected = st.selectbox(
        "Endpoint",
        options=range(len(endpoints)),
        format_func=lambda i: f"{endpoints[i][0]} {endpoints[i][1]} - {endpoints[i][2]}"
    )
    
    method, path, desc = endpoints[selected]
    
    st.caption(desc)
    
    # Request body for POST
    body = {}
    if method == "POST":
        if "sequence" in path:
            body = {"sequence": "ATGCGTACGTAGCTAGCTAGCTA", "type": "DNA"}
        elif "admet" in path:
            body = {"smiles": "CCO"}
        elif "assistant" in path:
            body = {"question": "What genes are associated with breast cancer?"}
        
        body_str = st.text_area("Request Body (JSON)", value=json.dumps(body, indent=2), height=150)
        try:
            body = json.loads(body_str)
        except:
            st.error("Invalid JSON")
    
    # API Key
    api_key = st.text_input("API Key", "geneai_demo_key_12345", type="password")
    
    if st.button("🚀 Send Request", type="primary"):
        url = f"{api_base_url}{path}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Show curl command
        curl_cmd = f"""curl -X {method} \\
  -H "Authorization: Bearer {api_key}" \\
  -H "Content-Type: application/json" \\
  {'-d \'' + json.dumps(body) + '\'' if method == 'POST' else ''} \\
  {url}"""
        st.code(curl_cmd)
        
        # Send actual request
        try:
            with st.spinner("Sending request..."):
                if method == "GET":
                    response = requests.get(url, headers=headers, timeout=30)
                else:
                    response = requests.post(url, headers=headers, json=body, timeout=60)
            
            st.subheader(f"Response (Status: {response.status_code})")
            
            try:
                response_json = response.json()
                st.json(response_json)
            except:
                st.text(response.text)
                
            # Show response time
            st.caption(f"Response time: {response.elapsed.total_seconds():.3f}s")
            
        except requests.exceptions.ConnectionError:
            st.error(f"❌ Could not connect to API server at {api_base_url}. Make sure the server is running.")
        except requests.exceptions.Timeout:
            st.error("❌ Request timed out")
        except requests.exceptions.RequestException as e:
            st.error(f"❌ Request failed: {e}")


def render_analytics_tab(api: GeneAIAPI):
    """Render API analytics."""
    st.subheader("API Analytics")
    
    st.info("Analytics would show request volume, latency, error rates, etc.")
    
    # Mock data
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Requests", "12,345")
    col2.metric("Success Rate", "99.2%")
    col3.metric("Avg Latency", "145ms")
    col4.metric("Active Keys", len([k for k in api.api_keys.values() if k.is_active]))
    
    # Charts would go here
    st.write("### Request Volume (Last 24h)")
    import pandas as pd
    df = pd.DataFrame({
        'hour': list(range(24)),
        'requests': [45, 32, 28, 15, 12, 20, 45, 120, 245, 380, 520, 610, 680, 720, 690, 650, 580, 520, 480, 410, 320, 210, 120, 65]
    })
    st.line_chart(df.set_index('hour'))
    
    st.write("### Top Endpoints")
    endpoint_data = pd.DataFrame({
        'endpoint': ['/genes/search', '/diseases/search', '/drugs/search', '/sequence/analyze', '/analysis/admet', '/assistant/ask'],
        'requests': [3200, 2100, 1800, 1500, 900, 600],
    })
    st.bar_chart(endpoint_data.set_index('endpoint'))


def render_settings_tab():
    """Render API settings."""
    st.subheader("API Settings")
    
    with st.form("settings_form"):
        st.write("### Server Settings")
        host = st.text_input("Host", "0.0.0.0")
        port = st.number_input("Port", 1000, 65535, 5000)
        workers = st.number_input("Workers", 1, 32, 4)
        timeout = st.number_input("Timeout (seconds)", 10, 300, 30)
        
        st.write("### Rate Limiting")
        default_limit = st.text_input("Default Limit", "1000 per hour")
        burst_limit = st.text_input("Burst Limit", "100 per minute")
        
        st.write("### CORS")
        cors_origins = st.text_area("Allowed Origins (one per line)", "http://localhost:3000\nhttp://localhost:8501")
        cors_methods = st.text_input("Allowed Methods", "GET,POST,PUT,DELETE,OPTIONS")
        
        st.write("### Security")
        require_https = st.checkbox("Require HTTPS in Production")
        api_key_header = st.text_input("API Key Header", "Authorization")
        
        if st.form_submit_button("Save Settings"):
            st.success("Settings saved (would persist to config file)")


def render():
    """Main render function."""
    render_rest_api_dashboard()


if __name__ == "__main__":
    render()