"""GeneAI Cloud Computing Integration - Phase 5.6."""
from __future__ import annotations

from geneai.cloud_integration.core import (
    CloudResourceManager,
    CloudConfig,
    CloudProvider,
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
    GCPStorage,
    AzureStorage,
    LocalStorage,
    LocalCompute,
    LocalBatch,
    InstanceState,
    JobStatus,
    create_storage,
    create_compute,
    create_batch,
    get_cloud_manager,
    init_cloud,
)
from geneai.cloud_integration.ui import (
    render_cloud_integration_dashboard,
    render as render_cloud_integration,
)

__all__ = [
    # Core
    "CloudResourceManager",
    "CloudConfig",
    "CloudProvider",
    "StorageClass",
    "StorageObject",
    "ComputeInstance",
    "JobDefinition",
    "JobExecution",
    "CloudStorage",
    "CloudCompute",
    "CloudBatch",
    "AWSStorage",
    "AWSCompute",
    "AWSBatch",
    "GCPStorage",
    "AzureStorage",
    "LocalStorage",
    "LocalCompute",
    "LocalBatch",
    "InstanceState",
    "JobStatus",
    "create_storage",
    "create_compute",
    "create_batch",
    "get_cloud_manager",
    "init_cloud",
    # UI
    "render_cloud_integration_dashboard",
    "render_cloud_integration",
]

__version__ = "5.6.0"