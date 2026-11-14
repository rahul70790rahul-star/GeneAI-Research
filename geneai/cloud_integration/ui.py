"""Streamlit UI for Cloud Computing Integration - Phase 5.6."""
from __future__ import annotations

import logging
import os
import time
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from typing import Any

from geneai.cloud_integration.core import (
    CloudProvider,
    CloudConfig,
    CloudResourceManager,
    StorageClass,
    StorageObject,
    ComputeInstance,
    JobDefinition,
    JobExecution,
    CloudStorage,
    CloudCompute,
    CloudBatch,
    AWSStorage,
    AWSCompute,
    AWSBatch,
    LocalStorage,
    create_storage,
    create_compute,
    create_batch,
    get_cloud_manager,
    init_cloud,
)

logger = logging.getLogger(__name__)


def render_cloud_integration_dashboard():
    """Render the cloud integration dashboard."""
    st.title("☁️ GeneAI Cloud Integration")
    st.caption("Multi-cloud storage, compute, and batch processing")
    
    # Initialize cloud manager
    if "cloud_manager" not in st.session_state:
        st.session_state.cloud_manager = get_cloud_manager()
    
    manager: CloudResourceManager = st.session_state.cloud_manager
    
    # Sidebar
    with st.sidebar:
        st.header("Cloud Status")
        
        # Provider selection
        provider = st.selectbox(
            "Active Provider",
            [CloudProvider.LOCAL, CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE],
            format_func=lambda p: p.value.upper(),
        )
        
        st.divider()
        
        # Storage stats
        st.subheader("Storage")
        try:
            storage = manager.get_storage(provider)
            st.metric("Provider", storage.__class__.__name__)
        except Exception as e:
            st.error(f"Storage error: {e}")
        
        st.divider()
        
        # Compute stats
        st.subheader("Compute")
        try:
            compute = manager.get_compute(provider)
            st.metric("Provider", compute.__class__.__name__)
        except Exception as e:
            st.error(f"Compute error: {e}")
        
        st.divider()
        
        # Batch stats
        st.subheader("Batch Processing")
        try:
            batch = manager.get_batch(provider)
            st.metric("Provider", batch.__class__.__name__)
        except Exception as e:
            st.error(f"Batch error: {e}")
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📦 Storage", "⚙️ Compute", "🔄 Batch Jobs", 
        "📊 Monitoring", "🔧 Configuration", "📈 Benchmarks"
    ])
    
    with tab1:
        render_storage_tab(manager, provider)
    
    with tab2:
        render_compute_tab(manager, provider)
    
    with tab3:
        render_batch_tab(manager, provider)
    
    with tab4:
        render_monitoring_tab(manager, provider)
    
    with tab5:
        render_configuration_tab(manager)
    
    with tab6:
        render_cloud_benchmarks_tab()


def render_storage_tab(manager: CloudResourceManager, provider: CloudProvider):
    """Render storage management tab."""
    st.subheader(f"📦 {provider.value.upper()} Storage")
    
    try:
        storage: CloudStorage = manager.get_storage(provider)
    except Exception as e:
        st.error(f"Failed to get storage: {e}")
        return
    
    # Bucket/Container management
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.write("### Buckets / Containers")
        
        with st.form("create_bucket"):
            bucket_name = st.text_input("Bucket Name", "geneai-data")
            storage_class = st.selectbox(
                "Storage Class",
                [StorageClass.STANDARD, StorageClass.INFREQUENT, 
                 StorageClass.ARCHIVE, StorageClass.INTELLIGENT],
                format_func=lambda s: s.value.replace("_", " ").title(),
            )
            region = st.text_input("Region", "us-east-1")
            
            if st.form_submit_button("Create Bucket"):
                try:
                    if storage.create_bucket(bucket_name, region):
                        st.success(f"Created bucket: {bucket_name}")
                        st.rerun()
                    else:
                        st.error("Failed to create bucket")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        # List buckets (for LocalStorage, show local directories)
        if isinstance(storage, LocalStorage):
            st.write("### Local Directories")
            import os
            for item in os.listdir(storage.base_path):
                item_path = os.path.join(storage.base_path, item)
                if os.path.isdir(item_path):
                    st.write(f"📁 {item}")
        else:
            st.info("Bucket listing not implemented for this provider demo")
    
    with col2:
        st.write("### Quick Actions")
        
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
        
        if st.button("📤 Upload File", use_container_width=True):
            st.session_state.show_upload = True
        
        if st.button("📁 Browse Objects", use_container_width=True):
            st.session_state.show_browse = True
    
    st.divider()
    
    # File upload
    if st.session_state.get("show_upload", False):
        st.write("### Upload File")
        
        with st.form("upload_file"):
            bucket = st.text_input("Bucket", "geneai-data")
            uploaded = st.file_uploader("Choose file", type=["txt", "csv", "json", "fasta", "vcf"])
            object_key = st.text_input("Object Key (path)", "uploads/")
            
            if st.form_submit_button("Upload"):
                if uploaded:
                    object_key = f"{object_key}{uploaded.name}"
                    try:
                        storage.upload_file(
                            bucket,
                            object_key,
                            uploaded.getvalue(),
                            content_type=uploaded.type,
                        )
                        st.success(f"Uploaded: {object_key}")
                        st.session_state.show_upload = False
                    except Exception as e:
                        st.error(f"Upload failed: {e}")
                else:
                    st.error("Please select a file")
        
        if st.button("Cancel Upload"):
            st.session_state.show_upload = False
            st.rerun()
    
    # Object browsing
    if st.session_state.get("show_browse", False):
        st.write("### Browse Objects")
        
        bucket = st.text_input("Bucket to Browse", "geneai-data", key="browse_bucket")
        prefix = st.text_input("Prefix Filter", "", key="browse_prefix")
        
        if st.button("List Objects"):
            try:
                objects = storage.list_objects(bucket, prefix)
                
                if objects:
                    df = pd.DataFrame([
                        {
                            "Key": obj.key,
                            "Size (MB)": round(obj.size / (1024*1024), 2),
                            "Modified": obj.last_modified,
                            "Storage Class": obj.storage_class.value if obj.storage_class else "N/A",
                            "ETag": obj.etag or "N/A",
                        }
                        for obj in objects
                    ])
                    st.dataframe(df, use_container_width=True)
                    
                    # Download option
                    selected = st.selectbox("Download object", [obj.key for obj in objects])
                    if st.button("Download Selected"):
                        try:
                            data = storage.download_file(bucket, selected)
                            st.download_button(
                                "Save File",
                                data,
                                file_name=selected.split("/")[-1],
                            )
                        except Exception as e:
                            st.error(f"Download failed: {e}")
                else:
                    st.info("No objects found")
            except Exception as e:
                st.error(f"List failed: {e}")
        
        if st.button("Close Browser"):
            st.session_state.show_browse = False
            st.rerun()
    
    st.divider()
    
    # Presigned URL generation
    st.write("### Presigned URLs")
    
    with st.form("presigned_url"):
        bucket = st.text_input("Bucket", "geneai-data", key="presigned_bucket")
        object_key = st.text_input("Object Key", "data/sample.csv", key="presigned_key")
        expiration = st.number_input("Expiration (seconds)", 60, 604800, 3600)
        operation = st.selectbox("Operation", ["get_object", "put_object"])
        
        if st.form_submit_button("Generate URL"):
            try:
                url = storage.generate_presigned_url(bucket, object_key, expiration, operation)
                st.success("Presigned URL generated:")
                st.code(url)
            except Exception as e:
                st.error(f"Failed: {e}")


def render_compute_tab(manager: CloudResourceManager, provider: CloudProvider):
    """Render compute management tab."""
    st.subheader(f"⚙️ {provider.value.upper()} Compute")
    
    try:
        compute: CloudCompute = manager.get_compute(provider)
    except Exception as e:
        st.error(f"Failed to get compute: {e}")
        return
    
    # Instance management
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.write("### Instances")
        
        with st.form("create_instance"):
            instance_id = st.text_input("Instance Name", "geneai-worker")
            instance_type = st.selectbox(
                "Instance Type",
                ["t3.micro", "t3.small", "t3.medium", "t3.large", "c5.large", "c5.xlarge", "r5.large"],
            )
            region = st.text_input("Region", "us-east-1")
            image_id = st.text_input("Image ID", "ami-0abcdef1234567890")
            
            if st.form_submit_button("Launch Instance"):
                try:
                    instance = compute.launch_instance(
                        instance_type=instance_type,
                        image_id=image_id,
                        region=region,
                        tags={"Name": instance_id, "Project": "GeneAI"},
                    )
                    st.success(f"Launched: {instance.instance_id}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Launch failed: {e}")
        
        # List instances
        try:
            instances = compute.list_instances()
            
            if instances:
                df = pd.DataFrame([
                    {
                        "ID": inst.instance_id,
                        "Type": inst.instance_type,
                        "State": inst.state.value,
                        "Region": inst.region,
                        "Launch Time": inst.launch_time,
                        "Public IP": inst.public_ip or "N/A",
                        "Private IP": inst.private_ip or "N/A",
                    }
                    for inst in instances
                ])
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No instances running")
        except Exception as e:
            st.error(f"List failed: {e}")
    
    with col2:
        st.write("### Instance Actions")
        
        try:
            instances = compute.list_instances()
            if instances:
                selected = st.selectbox("Select Instance", [i.instance_id for i in instances])
                
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("▶️ Start", use_container_width=True):
                        compute.start_instance(selected)
                        st.success("Started")
                        st.rerun()
                
                with col_b:
                    if st.button("⏹️ Stop", use_container_width=True):
                        compute.stop_instance(selected)
                        st.success("Stopped")
                        st.rerun()
                
                if st.button("🔄 Reboot", use_container_width=True):
                    compute.reboot_instance(selected)
                    st.success("Rebooted")
                    st.rerun()
                
                if st.button("🗑️ Terminate", use_container_width=True, type="secondary"):
                    compute.terminate_instance(selected)
                    st.success("Terminated")
                    st.rerun()
            else:
                st.info("No instances to manage")
        except Exception as e:
            st.error(f"Error: {e}")
    
    st.divider()
    
    # Instance metrics (mock for demo)
    st.write("### Instance Metrics")
    
    try:
        instances = compute.list_instances()
        if instances:
            selected = st.selectbox("Monitor Instance", [i.instance_id for i in instances], key="metric_instance")
            
            if st.button("Get Metrics"):
                metrics = compute.get_instance_metrics(selected)
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("CPU", f"{metrics.get('cpu_percent', 0):.1f}%")
                col2.metric("Memory", f"{metrics.get('memory_percent', 0):.1f}%")
                col3.metric("Disk I/O", f"{metrics.get('disk_io_mb', 0):.1f} MB/s")
                col4.metric("Network", f"{metrics.get('network_mb', 0):.1f} MB/s")
        else:
            st.info("Launch an instance to see metrics")
    except Exception as e:
        st.error(f"Metrics error: {e}")


def render_batch_tab(manager: CloudResourceManager, provider: CloudProvider):
    """Render batch processing tab."""
    st.subheader(f"🔄 {provider.value.upper()} Batch Processing")
    
    try:
        batch: CloudBatch = manager.get_batch(provider)
    except Exception as e:
        st.error(f"Failed to get batch: {e}")
        return
    
    # Job definition
    st.write("### Job Definitions")
    
    with st.form("create_job_def"):
        job_name = st.text_input("Job Name", "geneai-analysis")
        image = st.text_input("Docker Image", "geneai/analysis:latest")
        
        col1, col2 = st.columns(2)
        with col1:
            vcpus = st.number_input("vCPUs", 1, 64, 2)
            memory = st.number_input("Memory (GB)", 1, 256, 4)
        with col2:
            gpus = st.number_input("GPUs", 0, 8, 0)
            timeout = st.number_input("Timeout (seconds)", 60, 86400, 3600)
        
        command = st.text_area("Command", "python analyze.py --input /data/input.csv --output /data/output.json")
        env_vars = st.text_area("Environment Variables (KEY=VALUE per line)", "INPUT_BUCKET=geneai-data\nOUTPUT_BUCKET=geneai-results")
        
        if st.form_submit_button("Register Job Definition"):
            try:
                env_dict = {}
                for line in env_vars.strip().split("\n"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        env_dict[k.strip()] = v.strip()
                
                job_def = batch.register_job_definition(
                    name=job_name,
                    image=image,
                    vcpus=vcpus,
                    memory=memory,
                    command=command.split(),
                    environment=env_dict,
                    gpu_count=gpus,
                )
                st.success(f"Registered: {job_def.job_definition_id}")
            except Exception as e:
                st.error(f"Registration failed: {e}")
    
    st.divider()
    
    # Submit job
    st.write("### Submit Batch Job")
    
    with st.form("submit_job"):
        try:
            job_defs = batch.list_job_definitions()
            if job_defs:
                job_def = st.selectbox("Job Definition", [j.job_definition_id for j in job_defs])
            else:
                job_def = st.text_input("Job Definition ID", "geneai-analysis")
        except Exception:
            job_def = st.text_input("Job Definition ID", "geneai-analysis")
        
        job_name = st.text_input("Job Name", f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        queue = st.text_input("Queue", "geneai-queue")
        
        overrides = st.text_area("Overrides (JSON)", '{"command": ["python", "analyze.py", "--custom"]}')
        
        if st.form_submit_button("Submit Job"):
            try:
                import json
                override_dict = json.loads(overrides) if overrides else {}
                
                execution = batch.submit_job(
                    job_name=job_name,
                    job_definition=job_def,
                    queue=queue,
                    overrides=override_dict,
                )
                st.success(f"Submitted: {execution.execution_id}")
                st.rerun()
            except Exception as e:
                st.error(f"Submit failed: {e}")
    
    st.divider()
    
    # Job executions
    st.write("### Job Executions")
    
    try:
        executions = batch.list_executions()
        
        if executions:
            df = pd.DataFrame([
                {
                    "ID": exec.execution_id,
                    "Job": exec.job_name,
                    "Status": exec.status.value,
                    "Started": exec.start_time,
                    "Completed": exec.end_time or "Running",
                    "Duration (s)": round((exec.end_time - exec.start_time).total_seconds(), 1) if exec.end_time else "N/A",
                    "Exit Code": exec.exit_code if exec.exit_code is not None else "N/A",
                }
                for exec in executions
            ])
            st.dataframe(df, use_container_width=True)
            
            # Job details
            selected_exec = st.selectbox("View Details", [e.execution_id for e in executions])
            exec_obj = next((e for e in executions if e.execution_id == selected_exec), None)
            
            if exec_obj:
                st.write("#### Execution Details")
                st.json({
                    "execution_id": exec_obj.execution_id,
                    "job_name": exec_obj.job_name,
                    "status": exec_obj.status.value,
                    "start_time": exec_obj.start_time.isoformat() if exec_obj.start_time else None,
                    "end_time": exec_obj.end_time.isoformat() if exec_obj.end_time else None,
                    "exit_code": exec_obj.exit_code,
                    "logs": exec_obj.logs[:500] + "..." if exec_obj.logs and len(exec_obj.logs) > 500 else exec_obj.logs,
                })
        else:
            st.info("No job executions yet")
    except Exception as e:
        st.error(f"List failed: {e}")


def render_monitoring_tab(manager: CloudResourceManager, provider: CloudProvider):
    """Render monitoring tab."""
    st.subheader(f"📊 {provider.value.upper()} Monitoring")
    
    st.markdown("""
    Monitor cloud resource utilization, costs, and performance.
    """)
    
    # Cost estimation (mock)
    st.write("### Cost Estimation")
    
    with st.form("cost_estimate"):
        st.write("**Compute**")
        col1, col2, col3 = st.columns(3)
        instance_type = col1.selectbox("Instance", ["t3.micro", "t3.small", "t3.medium", "t3.large"])
        hours = col2.number_input("Hours/Month", 1, 730, 730)
        count = col3.number_input("Count", 1, 100, 1)
        
        st.write("**Storage**")
        col1, col2 = st.columns(2)
        storage_gb = col1.number_input("Storage (GB)", 1, 10000, 100)
        storage_class = col2.selectbox("Class", [c.value for c in StorageClass])
        
        st.write("**Data Transfer**")
        egress_gb = st.number_input("Egress (GB)", 0, 10000, 10)
        
        if st.form_submit_button("Estimate Cost"):
            # Mock pricing
            pricing = {
                "t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416, "t3.large": 0.0832,
            }
            storage_pricing = {
                "standard": 0.023, "infrequent": 0.0125, "archive": 0.004, "intelligent": 0.023,
            }
            egress_price = 0.09
            
            compute_cost = pricing.get(instance_type, 0.05) * hours * count
            storage_cost = storage_pricing.get(storage_class, 0.023) * storage_gb
            egress_cost = egress_price * egress_gb
            total = compute_cost + storage_cost + egress_cost
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Compute", f"${compute_cost:.2f}/mo")
            col2.metric("Storage", f"${storage_cost:.2f}/mo")
            col3.metric("Egress", f"${egress_cost:.2f}/mo")
            col4.metric("Total", f"${total:.2f}/mo", delta_color="off")
    
    st.divider()
    
    # Resource utilization charts (mock data)
    st.write("### Resource Utilization")
    
    import random
    dates = pd.date_range(end=datetime.now(), periods=24, freq='h')
    
    cpu_data = [random.uniform(10, 80) for _ in range(24)]
    mem_data = [random.uniform(20, 90) for _ in range(24)]
    net_data = [random.uniform(1, 50) for _ in range(24)]
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=cpu_data, name="CPU %", line=dict(color="blue")))
    fig.add_trace(go.Scatter(x=dates, y=mem_data, name="Memory %", line=dict(color="green")))
    fig.add_trace(go.Scatter(x=dates, y=net_data, name="Network MB/s", line=dict(color="red"), yaxis="y2"))
    
    fig.update_layout(
        title="24-Hour Resource Utilization",
        yaxis=dict(title="Percentage"),
        yaxis2=dict(title="MB/s", overlaying="y", side="right"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Alerts
    st.write("### Alerts & Notifications")
    
    alerts = [
        {"severity": "warning", "message": "CPU > 80% on instance i-12345", "time": "5 min ago"},
        {"severity": "info", "message": "Batch job completed: geneai-analysis-run-1", "time": "12 min ago"},
        {"severity": "critical", "message": "Disk space < 10% on storage volume", "time": "1 hour ago"},
        {"severity": "info", "message": "New instance launched: geneai-worker-2", "time": "2 hours ago"},
    ]
    
    for alert in alerts:
        if alert["severity"] == "critical":
            st.error(f"🔴 **{alert['message']}** - {alert['time']}")
        elif alert["severity"] == "warning":
            st.warning(f"🟡 **{alert['message']}** - {alert['time']}")
        else:
            st.info(f"🔵 **{alert['message']}** - {alert['time']}")


def render_configuration_tab(manager: CloudResourceManager):
    """Render configuration tab."""
    st.subheader("🔧 Cloud Configuration")
    
    st.markdown("""
    Manage cloud provider configurations, credentials, and settings.
    """)
    
    # Current config
    st.write("### Current Configuration")
    
    config = manager.get_config()
    
    with st.expander("📋 View Configuration", expanded=True):
        st.json({
            "provider": config.provider.value,
            "region": config.region,
            "profile": config.profile,
            "has_credentials": bool(config.access_key_id and config.secret_access_key),
            "endpoint_url": config.endpoint_url,
        })
    
    st.divider()
    
    # Add/Update provider config
    st.write("### Configure Provider")
    
    with st.form("provider_config"):
        provider = st.selectbox(
            "Provider",
            [CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE, CloudProvider.LOCAL],
        )
        
        region = st.text_input("Region", "us-east-1")
        profile = st.text_input("Profile (optional)", "")
        
        col1, col2 = st.columns(2)
        access_key = col1.text_input("Access Key ID", type="password")
        secret_key = col2.text_input("Secret Access Key", type="password")
        
        endpoint = st.text_input("Custom Endpoint (optional)", "")
        
        if st.form_submit_button("Save Configuration"):
            new_config = CloudConfig(
                provider=provider,
                region=region,
                profile=profile if profile else None,
                access_key_id=access_key if access_key else None,
                secret_access_key=secret_key if secret_key else None,
                endpoint_url=endpoint if endpoint else None,
            )
            
            manager.add_provider_config(new_config)
            st.success(f"Saved configuration for {provider.value.upper()}")
            st.rerun()
    
    st.divider()
    
    # Provider switching
    st.write("### Active Provider")
    
    current = manager.get_config().provider
    new_provider = st.selectbox(
        "Switch to",
        [CloudProvider.LOCAL, CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE],
        index=[CloudProvider.LOCAL, CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE].index(current),
        format_func=lambda p: p.value.upper(),
    )
    
    if st.button("Switch Provider"):
        manager.set_active_provider(new_provider)
        st.success(f"Switched to {new_provider.value.upper()}")
        st.rerun()
    
    st.divider()
    
    # Test connections
    st.write("### Connection Tests")
    
    for provider in [CloudProvider.LOCAL, CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE]:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"**{provider.value.upper()}**")
        with col2:
            if st.button("Test", key=f"test_{provider.value}"):
                try:
                    storage = manager.get_storage(provider)
                    compute = manager.get_compute(provider)
                    st.success("✅ Connected")
                except Exception as e:
                    st.error(f"❌ Failed: {e}")


def render_cloud_benchmarks_tab():
    """Render cloud benchmarks tab."""
    st.subheader("📈 Cloud Benchmarks")
    
    st.markdown("""
    Run benchmarks to compare cloud provider performance.
    """)
    
    benchmarks = {
        "Storage Upload": "storage_upload",
        "Storage Download": "storage_download",
        "Instance Launch": "instance_launch",
        "Batch Job Submit": "batch_submit",
        "Network Latency": "network_latency",
    }
    
    selected = st.multiselect(
        "Select Benchmarks",
        list(benchmarks.keys()),
        default=["Storage Upload", "Instance Launch"]
    )
    
    provider = st.selectbox(
        "Provider",
        [CloudProvider.LOCAL, CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE],
        format_func=lambda p: p.value.upper(),
    )
    
    if st.button("Run Benchmarks", type="primary"):
        results = {}
        
        for bench_name in selected:
            with st.spinner(f"Running {bench_name}..."):
                if bench_name == "Storage Upload":
                    results[bench_name] = run_storage_upload_benchmark(provider)
                elif bench_name == "Storage Download":
                    results[bench_name] = run_storage_download_benchmark(provider)
                elif bench_name == "Instance Launch":
                    results[bench_name] = run_instance_launch_benchmark(provider)
                elif bench_name == "Batch Job Submit":
                    results[bench_name] = run_batch_submit_benchmark(provider)
                elif bench_name == "Network Latency":
                    results[bench_name] = run_network_latency_benchmark(provider)
        
        # Display results
        st.write("### Benchmark Results")
        
        for name, result in results.items():
            with st.expander(f"📊 {name}", expanded=True):
                if "error" in result:
                    st.error(result["error"])
                else:
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Duration", f"{result.get('duration', 0):.3f}s")
                    col2.metric("Throughput", result.get('throughput', 'N/A'))
                    col3.metric("Success", "✅" if result.get('success') else "❌")
                    
                    if "details" in result:
                        st.json(result["details"])


def run_storage_upload_benchmark(provider: CloudProvider) -> dict[str, Any]:
    """Run storage upload benchmark."""
    import tempfile
    import os
    
    try:
        manager = get_cloud_manager()
        storage = manager.get_storage(provider)
        
        # Create test file (10MB)
        test_data = os.urandom(10 * 1024 * 1024)
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(test_data)
            temp_path = f.name
        
        bucket = "geneai-benchmark"
        key = f"benchmark/{datetime.now().strftime('%Y%m%d-%H%M%S')}.bin"
        
        try:
            storage.create_bucket(bucket, "us-east-1")
        except Exception:
            pass  # Bucket may exist
        
        start = time.time()
        storage.upload_file(bucket, key, test_data)
        duration = time.time() - start
        
        # Cleanup
        storage.delete_object(bucket, key)
        os.unlink(temp_path)
        
        return {
            "duration": duration,
            "throughput": f"{10 / duration:.1f} MB/s",
            "success": True,
            "details": {"file_size_mb": 10},
        }
    except Exception as e:
        return {"error": str(e), "success": False}


def run_storage_download_benchmark(provider: CloudProvider) -> dict[str, Any]:
    """Run storage download benchmark."""
    try:
        manager = get_cloud_manager()
        storage = manager.get_storage(provider)
        
        bucket = "geneai-benchmark"
        key = f"benchmark/{datetime.now().strftime('%Y%m%d-%H%M%S')}.bin"
        
        # Upload first
        test_data = os.urandom(10 * 1024 * 1024)
        storage.upload_file(bucket, key, test_data)
        
        start = time.time()
        storage.download_file(bucket, key)
        duration = time.time() - start
        
        storage.delete_object(bucket, key)
        
        return {
            "duration": duration,
            "throughput": f"{10 / duration:.1f} MB/s",
            "success": True,
            "details": {"file_size_mb": 10},
        }
    except Exception as e:
        return {"error": str(e), "success": False}


def run_instance_launch_benchmark(provider: CloudProvider) -> dict[str, Any]:
    """Run instance launch benchmark."""
    try:
        manager = get_cloud_manager()
        compute = manager.get_compute(provider)
        
        start = time.time()
        instance = compute.launch_instance(
            instance_type="t3.micro",
            image_id="ami-test",
            region="us-east-1",
        )
        launch_time = time.time() - start
        
        # Terminate immediately
        compute.terminate_instance(instance.instance_id)
        
        return {
            "duration": launch_time,
            "throughput": f"1 instance in {launch_time:.1f}s",
            "success": True,
            "details": {"instance_type": "t3.micro"},
        }
    except Exception as e:
        return {"error": str(e), "success": False}


def run_batch_submit_benchmark(provider: CloudProvider) -> dict[str, Any]:
    """Run batch job submit benchmark."""
    try:
        manager = get_cloud_manager()
        batch = manager.get_batch(provider)
        
        # Register job def
        job_def = batch.register_job_definition(
            name="benchmark-job",
            image="alpine:latest",
            vcpus=1,
            memory=1,
            command=["echo", "hello"],
        )
        
        start = time.time()
        execution = batch.submit_job(
            job_name="benchmark-run",
            job_definition=job_def.job_definition_id,
            queue="default",
        )
        submit_time = time.time() - start
        
        return {
            "duration": submit_time,
            "throughput": f"1 job in {submit_time:.3f}s",
            "success": True,
            "details": {"job_def": job_def.job_definition_id},
        }
    except Exception as e:
        return {"error": str(e), "success": False}


def run_network_latency_benchmark(provider: CloudProvider) -> dict[str, Any]:
    """Run network latency benchmark."""
    import socket
    import time
    
    try:
        # Test localhost latency as proxy
        latencies = []
        for _ in range(10):
            start = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            try:
                sock.connect(("127.0.0.1", 80))
            except Exception:
                pass
            finally:
                sock.close()
            latencies.append((time.time() - start) * 1000)
        
        avg_latency = sum(latencies) / len(latencies)
        
        return {
            "duration": avg_latency / 1000,
            "throughput": f"{avg_latency:.1f} ms avg",
            "success": True,
            "details": {"latencies_ms": latencies},
        }
    except Exception as e:
        return {"error": str(e), "success": False}


def render():
    """Main render function."""
    render_cloud_integration_dashboard()


if __name__ == "__main__":
    render()