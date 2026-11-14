"""Cloud Computing Integration - Phase 5.6 Core."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Module-level boto3 reference for test patching
_boto3 = None
boto3 = None
try:
    import boto3 as _boto3
except ImportError:
    pass


def _import_boto3():
    """Lazy import of boto3."""
    global _boto3, boto3
    # Use module-level boto3 if already set (e.g., by test patch)
    if boto3 is not None:
        return boto3
    if _boto3 is not None:
        return _boto3
    try:
        import boto3 as _boto3_module
        _boto3 = _boto3_module
        return _boto3
    except ImportError:
        raise RuntimeError("boto3 not installed. Install with: pip install boto3")


class CloudProvider(Enum):
    """Supported cloud providers."""
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    LOCAL = "local"


class StorageClass(Enum):
    """Storage classes for cost optimization."""
    STANDARD = "STANDARD"
    INTELLIGENT_TIERING = "INTELLIGENT_TIERING"
    STANDARD_IA = "STANDARD_IA"
    ONE_ZONE_IA = "ONE_ZONE_IA"
    GLACIER = "GLACIER"
    GLACIER_IR = "GLACIER_IR"
    DEEP_ARCHIVE = "DEEP_ARCHIVE"
    
    # Aliases for test compatibility
    INFREQUENT = "INFREQUENT_ACCESS"
    ARCHIVE = "ARCHIVE"
    INTELLIGENT = "INTELLIGENT_TIERING"


class InstanceState(Enum):
    """Compute instance states."""
    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    SHUTTING_DOWN = "shutting-down"
    TERMINATED = "terminated"


class JobStatus(Enum):
    """Batch job statuses."""
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    RUNNABLE = "RUNNABLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass
class CloudConfig:
    """Cloud provider configuration."""
    provider: CloudProvider
    region: str = "us-east-1"
    credentials: dict[str, str] = field(default_factory=dict)
    bucket_name: str = ""
    project_id: str = ""
    endpoint_url: str = ""
    # Direct credentials for test compatibility
    access_key_id: str = ""
    secret_access_key: str = ""
    
    def __post_init__(self):
        # Sync direct credentials with credentials dict
        if self.access_key_id:
            self.credentials['access_key_id'] = self.access_key_id
        if self.secret_access_key:
            self.credentials['secret_access_key'] = self.secret_access_key
    
    # Properties for test compatibility
    @property
    def access_key_id(self) -> str:
        return self.credentials.get('access_key_id', '')
    
    @access_key_id.setter
    def access_key_id(self, value: str):
        self.credentials['access_key_id'] = value
        self.__dict__['access_key_id'] = value
    
    @property
    def secret_access_key(self) -> str:
        return self.credentials.get('secret_access_key', '')
    
    @secret_access_key.setter
    def secret_access_key(self, value: str):
        self.credentials['secret_access_key'] = value
        self.__dict__['secret_access_key'] = value
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "region": self.region,
            "credentials": self.credentials,
            "bucket_name": self.bucket_name,
            "project_id": self.project_id,
            "endpoint_url": self.endpoint_url,
        }


@dataclass
class StorageObject:
    """Represents a stored object."""
    key: str
    size: int
    last_modified: datetime
    etag: str
    storage_class: StorageClass = StorageClass.STANDARD
    metadata: dict[str, str] = field(default_factory=dict)
    version_id: str | None = None
    
    # Property for test compatibility
    @property
    def content_type(self) -> str:
        return self.metadata.get('content_type', 'application/octet-stream')


@dataclass
class ComputeInstance:
    """Cloud compute instance."""
    instance_id: str
    instance_type: str
    state: InstanceState | str
    region: str
    public_ip: str | None = None
    private_ip: str | None = None
    launch_time: datetime | str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if isinstance(self.state, str):
            try:
                self.state = InstanceState(self.state)
            except ValueError:
                pass
        if isinstance(self.launch_time, str):
            self.launch_time = datetime.fromisoformat(self.launch_time.replace('Z', '+00:00'))


@dataclass
class JobDefinition:
    """Batch job definition."""
    job_definition_id: str = ""
    name: str = ""
    image: str = ""
    command: list[str] = field(default_factory=list)
    vcpus: int = 1
    memory: int = 2
    gpu_count: int = 0
    environment: dict[str, str] = field(default_factory=dict)
    volumes: list[dict[str, Any]] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.job_definition_id:
            self.job_definition_id = f"job-def-{uuid.uuid4().hex[:8]}"


@dataclass
class JobExecution:
    """Batch job execution."""
    execution_id: str
    job_name: str
    status: JobStatus | str
    start_time: datetime | None = None
    end_time: datetime | None = None
    logs: str = ""
    exit_code: int | None = None
    
    def __post_init__(self):
        if isinstance(self.status, str):
            try:
                self.status = JobStatus(self.status)
            except ValueError:
                pass


class CloudStorage(ABC):
    """Abstract cloud storage interface."""
    
    @abstractmethod
    def create_bucket(self, bucket_name: str, region: str = "") -> bool:
        """Create a storage bucket."""
        pass
    
    @abstractmethod
    def upload_file(self, bucket_name: str, key: str, data: bytes, 
                    content_type: str = "application/octet-stream") -> bool:
        """Upload a file to cloud storage."""
        pass
    
    @abstractmethod
    def download_file(self, bucket_name: str, key: str) -> bytes:
        """Download a file from cloud storage."""
        pass
    
    @abstractmethod
    def delete_object(self, bucket_name: str, key: str) -> bool:
        """Delete an object from cloud storage."""
        pass
    
    @abstractmethod
    def list_objects(self, bucket_name: str, prefix: str = "") -> list[StorageObject]:
        """List objects in bucket."""
        pass
    
    @abstractmethod
    def object_exists(self, bucket_name: str, key: str) -> bool:
        """Check if object exists."""
        pass
    
    @abstractmethod
    def get_object_metadata(self, bucket_name: str, key: str) -> StorageObject | None:
        """Get object metadata."""
        pass
    
    @abstractmethod
    def generate_presigned_url(self, bucket_name: str, key: str, expiration: int = 3600) -> str:
        """Generate presigned URL for object access."""
        pass


class CloudCompute(ABC):
    """Abstract cloud compute interface."""
    
    @abstractmethod
    def create_instance(self, instance_type: str, image_id: str,
                        key_name: str = "", security_groups: list[str] = None,
                        user_data: str = "", tags: dict[str, str] = None) -> ComputeInstance:
        """Create a compute instance."""
        pass
    
    @abstractmethod
    def terminate_instance(self, instance_id: str) -> bool:
        """Terminate a compute instance."""
        pass
    
    @abstractmethod
    def get_instance(self, instance_id: str) -> ComputeInstance | None:
        """Get instance details."""
        pass
    
    @abstractmethod
    def list_instances(self, filters: dict[str, str] = None) -> list[ComputeInstance]:
        """List instances."""
        pass


class CloudBatch(ABC):
    """Abstract cloud batch processing interface."""
    
    @abstractmethod
    def register_job_definition(self, name: str, image: str,
                                vcpus: int, memory: int,
                                command: list[str],
                                environment: dict[str, str] = None,
                                gpu_count: int = 0) -> JobDefinition:
        """Register a job definition."""
        pass
    
    @abstractmethod
    def submit_job(self, job_name: str, job_definition: str,
                   queue: str, parameters: dict[str, str] = None,
                   depends_on: list[str] = None) -> JobExecution:
        """Submit a batch job."""
        pass
    
    @abstractmethod
    def get_job_execution(self, execution_id: str) -> JobExecution | None:
        """Get job execution status."""
        pass
    
    @abstractmethod
    def wait_for_job(self, execution_id: str, timeout: int = 3600) -> JobExecution:
        """Wait for job completion."""
        pass


# Local filesystem implementation (for development/testing)
class LocalStorage(CloudStorage):
    """Local filesystem storage implementation."""
    
    def __init__(self, base_path: str | Path = None):
        # If base_path is provided, use it directly; otherwise use temp dir with subfolder
        if base_path is not None:
            self.base_path = Path(base_path)
        else:
            self.base_path = Path(tempfile.gettempdir()) / "geneai_local_storage"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._buckets: set[str] = set()
    
    def _get_bucket_path(self, bucket_name: str) -> Path:
        return self.base_path / bucket_name
    
    def _get_full_path(self, bucket_name: str, key: str) -> Path:
        return self._get_bucket_path(bucket_name) / key
    
    def create_bucket(self, bucket_name: str, region: str = "") -> bool:
        bucket_path = self._get_bucket_path(bucket_name)
        bucket_path.mkdir(parents=True, exist_ok=True)
        self._buckets.add(bucket_name)
        return True
    
    def upload_file(self, bucket_name: str, key: str, data: bytes, 
                    content_type: str = "application/octet-stream") -> bool:
        if bucket_name not in self._buckets:
            raise ValueError(f"Bucket {bucket_name} does not exist")
        
        dest = self._get_full_path(bucket_name, key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        
        # Store metadata
        meta_file = dest.with_suffix(dest.suffix + '.meta')
        meta_file.write_text(json.dumps({'content_type': content_type}))
        return True
    
    def download_file(self, bucket_name: str, key: str) -> bytes:
        if bucket_name not in self._buckets:
            raise ValueError(f"Bucket {bucket_name} does not exist")
        
        path = self._get_full_path(bucket_name, key)
        if not path.exists():
            raise FileNotFoundError(f"Object {key} not found in bucket {bucket_name}")
        return path.read_bytes()
    
    def delete_object(self, bucket_name: str, key: str) -> bool:
        if bucket_name not in self._buckets:
            return False
        
        path = self._get_full_path(bucket_name, key)
        meta_file = path.with_suffix(path.suffix + '.meta')
        
        if path.exists():
            path.unlink()
            if meta_file.exists():
                meta_file.unlink()
            return True
        return False
    
    def list_objects(self, bucket_name: str, prefix: str = "") -> list[StorageObject]:
        if bucket_name not in self._buckets:
            return []
        
        objects = []
        prefix_path = self._get_bucket_path(bucket_name) / prefix
        
        if prefix_path.is_file():
            paths = [prefix_path]
        else:
            paths = list(prefix_path.rglob("*"))
        
        for path in paths:
            if path.is_file() and not path.suffix == '.meta':
                rel_path = path.relative_to(self._get_bucket_path(bucket_name))
                stat = path.stat()
                
                # Read metadata
                meta_file = path.with_suffix(path.suffix + '.meta')
                metadata = {}
                content_type = 'application/octet-stream'
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text())
                        metadata = meta
                        content_type = meta.get('content_type', content_type)
                    except Exception:
                        pass
                
                # Use forward slashes for cross-platform compatibility
                key_str = str(rel_path).replace('\\', '/')
                
                objects.append(StorageObject(
                    key=key_str,
                    size=stat.st_size,
                    last_modified=datetime.fromtimestamp(stat.st_mtime),
                    etag=hashlib.md5(path.read_bytes()).hexdigest(),
                    storage_class=StorageClass.STANDARD,
                    metadata={**metadata, 'content_type': content_type},
                ))
        return objects
    
    def object_exists(self, bucket_name: str, key: str) -> bool:
        if bucket_name not in self._buckets:
            return False
        path = self._get_full_path(bucket_name, key)
        return path.exists()
    
    def get_object_metadata(self, bucket_name: str, key: str) -> StorageObject | None:
        if bucket_name not in self._buckets:
            return None
        path = self._get_full_path(bucket_name, key)
        if not path.exists():
            return None
        
        stat = path.stat()
        meta_file = path.with_suffix(path.suffix + '.meta')
        metadata = {}
        content_type = 'application/octet-stream'
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                metadata = meta
                content_type = meta.get('content_type', content_type)
            except Exception:
                pass
        
        return StorageObject(
            key=key,
            size=stat.st_size,
            last_modified=datetime.fromtimestamp(stat.st_mtime),
            etag=hashlib.md5(path.read_bytes()).hexdigest(),
            storage_class=StorageClass.STANDARD,
            metadata={**metadata, 'content_type': content_type},
        )
    
    def generate_presigned_url(self, bucket_name: str, key: str, expiration: int = 3600) -> str:
        path = self._get_full_path(bucket_name, key)
        return path.as_uri()


class LocalCompute(CloudCompute):
    """Local compute implementation (simulated)."""
    
    def __init__(self):
        self._instances: dict[str, ComputeInstance] = {}
    
    def create_instance(self, instance_type: str, image_id: str,
                        key_name: str = "", security_groups: list[str] = None,
                        user_data: str = "", tags: dict[str, str] = None) -> ComputeInstance:
        instance_id = f"i-local-{uuid.uuid4().hex[:8]}"
        instance = ComputeInstance(
            instance_id=instance_id,
            instance_type=instance_type,
            state=InstanceState.RUNNING,
            region="local",
            launch_time=datetime.now(),
            public_ip="127.0.0.1",
            private_ip="127.0.0.1",
            tags=tags or {},
        )
        self._instances[instance_id] = instance
        return instance
    
    def terminate_instance(self, instance_id: str) -> bool:
        if instance_id in self._instances:
            self._instances[instance_id].state = InstanceState.TERMINATED
            del self._instances[instance_id]
            return True
        return False
    
    def get_instance(self, instance_id: str) -> ComputeInstance | None:
        return self._instances.get(instance_id)
    
    def list_instances(self, filters: dict[str, str] = None) -> list[ComputeInstance]:
        instances = list(self._instances.values())
        if filters:
            filtered = []
            for inst in instances:
                match = True
                for k, v in filters.items():
                    if k == 'state' and inst.state != v:
                        match = False
                        break
                    elif k == 'instance_type' and inst.instance_type != v:
                        match = False
                        break
                if match:
                    filtered.append(inst)
            return filtered
        return instances


class LocalBatch(CloudBatch):
    """Local batch implementation (simulated)."""
    
    def __init__(self):
        self._job_definitions: dict[str, JobDefinition] = {}
        self._executions: dict[str, JobExecution] = {}
    
    def register_job_definition(self, name: str, image: str,
                                vcpus: int, memory: int,
                                command: list[str],
                                environment: dict[str, str] = None,
                                gpu_count: int = 0) -> JobDefinition:
        job_def = JobDefinition(
            name=name,
            image=image,
            vcpus=vcpus,
            memory=memory,
            command=command,
            environment=environment or {},
            gpu_count=gpu_count,
        )
        self._job_definitions[job_def.job_definition_id] = job_def
        return job_def
    
    def submit_job(self, job_name: str, job_definition: str,
                   queue: str, parameters: dict[str, str] = None,
                   depends_on: list[str] = None) -> JobExecution:
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"
        execution = JobExecution(
            execution_id=execution_id,
            job_name=job_name,
            status=JobStatus.RUNNING,
            start_time=datetime.now(),
        )
        self._executions[execution_id] = execution
        return execution
    
    def get_job_execution(self, execution_id: str) -> JobExecution | None:
        return self._executions.get(execution_id)
    
    def wait_for_job(self, execution_id: str, timeout: int = 3600) -> JobExecution:
        execution = self.get_job_execution(execution_id)
        if execution:
            execution.status = JobStatus.SUCCEEDED
            execution.end_time = datetime.now()
            execution.exit_code = 0
        return execution


# AWS Implementation
class AWSStorage(CloudStorage):
    """AWS S3 storage implementation."""
    
    def __init__(self, config: CloudConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            boto3 = _import_boto3()
            self._client = boto3.client(
                's3',
                region_name=self.config.region,
                endpoint_url=self.config.endpoint_url or None,
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
            )
        return self._client
    
    def create_bucket(self, bucket_name: str, region: str = "") -> bool:
        client = self._get_client()
        try:
            if region and region != 'us-east-1':
                client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
            else:
                client.create_bucket(Bucket=bucket_name)
            return True
        except Exception:
            return False
    
    def upload_file(self, bucket_name: str, key: str, data: bytes, 
                    content_type: str = "application/octet-stream") -> bool:
        client = self._get_client()
        try:
            client.put_object(Bucket=bucket_name, Key=key, Body=data, ContentType=content_type)
            return True
        except Exception:
            return False
    
    def download_file(self, bucket_name: str, key: str) -> bytes:
        client = self._get_client()
        response = client.get_object(Bucket=bucket_name, Key=key)
        return response['Body'].read()
    
    def delete_object(self, bucket_name: str, key: str) -> bool:
        client = self._get_client()
        try:
            client.delete_object(Bucket=bucket_name, Key=key)
            return True
        except Exception:
            return False
    
    def list_objects(self, bucket_name: str, prefix: str = "") -> list[StorageObject]:
        client = self._get_client()
        objects = []
        
        # Use list_objects_v2 directly for compatibility with test mocks
        response = client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        for obj in response.get('Contents', []):
            storage_class = obj.get('StorageClass', 'STANDARD')
            try:
                sc = StorageClass(storage_class)
            except ValueError:
                sc = StorageClass.STANDARD
            
            objects.append(StorageObject(
                key=obj['Key'],
                size=obj['Size'],
                last_modified=obj['LastModified'],
                etag=obj['ETag'].strip('"'),
                storage_class=sc,
            ))
        return objects
    
    def object_exists(self, bucket_name: str, key: str) -> bool:
        client = self._get_client()
        try:
            client.head_object(Bucket=bucket_name, Key=key)
            return True
        except Exception:
            return False
    
    def get_object_metadata(self, bucket_name: str, key: str) -> StorageObject | None:
        client = self._get_client()
        try:
            response = client.head_object(Bucket=bucket_name, Key=key)
            storage_class = response.get('StorageClass', 'STANDARD')
            try:
                sc = StorageClass(storage_class)
            except ValueError:
                sc = StorageClass.STANDARD
            
            return StorageObject(
                key=key,
                size=response['ContentLength'],
                last_modified=response['LastModified'],
                etag=response['ETag'].strip('"'),
                storage_class=sc,
                metadata=response.get('Metadata', {}),
            )
        except Exception:
            return None
    
    def generate_presigned_url(self, bucket_name: str, key: str, expiration: int = 3600) -> str:
        client = self._get_client()
        return client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': key},
            ExpiresIn=expiration
        )


class AWSCompute(CloudCompute):
    """AWS EC2 compute implementation."""
    
    def __init__(self, config: CloudConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            boto3 = _import_boto3()
            self._client = boto3.client(
                'ec2',
                region_name=self.config.region,
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
            )
        return self._client
    
    def create_instance(self, instance_type: str, image_id: str,
                        key_name: str = "", security_groups: list[str] = None,
                        user_data: str = "", tags: dict[str, str] = None) -> ComputeInstance:
        client = self._get_client()
        
        run_args = {
            'ImageId': image_id,
            'InstanceType': instance_type,
            'MinCount': 1,
            'MaxCount': 1,
        }
        
        if key_name:
            run_args['KeyName'] = key_name
        if security_groups:
            run_args['SecurityGroupIds'] = security_groups
        if user_data:
            run_args['UserData'] = user_data
        
        if tags:
            run_args['TagSpecifications'] = [{
                'ResourceType': 'instance',
                'Tags': [{'Key': k, 'Value': v} for k, v in tags.items()]
            }]
        
        response = client.run_instances(**run_args)
        instance = response['Instances'][0]
        
        return ComputeInstance(
            instance_id=instance['InstanceId'],
            instance_type=instance['InstanceType'],
            state=InstanceState(instance['State']['Name']),
            region=self.config.region,
            public_ip=instance.get('PublicIpAddress'),
            private_ip=instance.get('PrivateIpAddress'),
            launch_time=instance.get('LaunchTime'),
            tags=tags or {},
        )
    
    def terminate_instance(self, instance_id: str) -> bool:
        client = self._get_client()
        try:
            client.terminate_instances(InstanceIds=[instance_id])
            return True
        except Exception:
            return False
    
    def get_instance(self, instance_id: str) -> ComputeInstance | None:
        client = self._get_client()
        try:
            response = client.describe_instances(InstanceIds=[instance_id])
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}
                    return ComputeInstance(
                        instance_id=instance['InstanceId'],
                        instance_type=instance['InstanceType'],
                        state=InstanceState(instance['State']['Name']),
                        region=self.config.region,
                        public_ip=instance.get('PublicIpAddress'),
                        private_ip=instance.get('PrivateIpAddress'),
                        launch_time=instance.get('LaunchTime'),
                        tags=tags,
                    )
        except Exception:
            pass
        return None
    
    def list_instances(self, filters: dict[str, str] = None) -> list[ComputeInstance]:
        client = self._get_client()
        
        filter_list = []
        if filters:
            for k, v in filters.items():
                filter_list.append({'Name': k, 'Values': [v]})
        
        try:
            response = client.describe_instances(Filters=filter_list)
            instances = []
            
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}
                    instances.append(ComputeInstance(
                        instance_id=instance['InstanceId'],
                        instance_type=instance['InstanceType'],
                        state=InstanceState(instance['State']['Name']),
                        region=self.config.region,
                        public_ip=instance.get('PublicIpAddress'),
                        private_ip=instance.get('PrivateIpAddress'),
                        launch_time=instance.get('LaunchTime'),
                        tags=tags,
                    ))
            return instances
        except Exception:
            return []


class AWSBatch(CloudBatch):
    """AWS Batch implementation."""
    
    def __init__(self, config: CloudConfig):
        self.config = config
        self._batch_client = None
        self._ecr_client = None
    
    def _get_batch_client(self):
        if self._batch_client is None:
            boto3 = _import_boto3()
            self._batch_client = boto3.client(
                'batch',
                region_name=self.config.region,
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
            )
        return self._batch_client
    
    def register_job_definition(self, name: str, image: str,
                                vcpus: int, memory: int,
                                command: list[str],
                                environment: dict[str, str] = None,
                                gpu_count: int = 0) -> JobDefinition:
        client = self._get_batch_client()
        
        container_props = {
            'image': image,
            'vcpus': vcpus,
            'memory': memory * 1024,
            'command': command,
            'environment': [{'name': k, 'value': v} for k, v in (environment or {}).items()],
        }
        
        if gpu_count > 0:
            container_props['resourceRequirements'] = [
                {'type': 'GPU', 'value': str(gpu_count)}
            ]
        
        response = client.register_job_definition(
            jobDefinitionName=name,
            type='container',
            containerProperties=container_props,
        )
        
        # Extract job definition name from ARN
        arn = response['jobDefinitionArn']
        job_def_name = arn.split('/')[-1].split(':')[0]
        
        return JobDefinition(
            job_definition_id=job_def_name,
            name=name,
            image=image,
            vcpus=vcpus,
            memory=memory,
            command=command,
            environment=environment or {},
            gpu_count=gpu_count,
        )
    
    def submit_job(self, job_name: str, job_definition: str,
                   queue: str, parameters: dict[str, str] = None,
                   depends_on: list[str] = None) -> JobExecution:
        client = self._get_batch_client()
        
        submit_args = {
            'jobName': job_name,
            'jobQueue': queue,
            'jobDefinition': job_definition,
        }
        
        if parameters:
            submit_args['parameters'] = parameters
        if depends_on:
            submit_args['dependsOn'] = [{'jobId': jid} for jid in depends_on]
        
        response = client.submit_job(**submit_args)
        
        return JobExecution(
            execution_id=response['jobId'],
            job_name=job_name,
            status=JobStatus.SUBMITTED,
            start_time=datetime.now(),
        )
    
    def get_job_execution(self, execution_id: str) -> JobExecution | None:
        client = self._get_batch_client()
        
        try:
            response = client.describe_jobs(jobs=[execution_id])
            if not response['jobs']:
                return None
            
            job = response['jobs'][0]
            return JobExecution(
                execution_id=job['jobId'],
                job_name=job['jobName'],
                status=JobStatus(job['status']),
                start_time=job.get('startedAt'),
                end_time=job.get('stoppedAt'),
                logs="",
                exit_code=job.get('container', {}).get('exitCode'),
            )
        except Exception:
            return None
    
    def wait_for_job(self, execution_id: str, timeout: int = 3600) -> JobExecution:
        import time
        start = time.time()
        
        while time.time() - start < timeout:
            execution = self.get_job_execution(execution_id)
            if execution and execution.status in [JobStatus.SUCCEEDED, JobStatus.FAILED]:
                return execution
            time.sleep(10)
        
        return self.get_job_execution(execution_id)


# GCP Implementation (placeholder)
class GCPStorage(CloudStorage):
    """GCP Cloud Storage implementation."""
    
    def __init__(self, config: CloudConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from google.cloud import storage
                self._client = storage.Client(
                    project=self.config.project_id,
                )
            except ImportError:
                raise RuntimeError("google-cloud-storage not installed")
        return self._client
    
    def create_bucket(self, bucket_name: str, region: str = "") -> bool:
        raise NotImplementedError("GCP storage not fully implemented")
    
    def upload_file(self, bucket_name: str, key: str, data: bytes, 
                    content_type: str = "application/octet-stream") -> bool:
        raise NotImplementedError("GCP storage not fully implemented")
    
    def download_file(self, bucket_name: str, key: str) -> bytes:
        raise NotImplementedError("GCP storage not fully implemented")
    
    def delete_object(self, bucket_name: str, key: str) -> bool:
        raise NotImplementedError("GCP storage not fully implemented")
    
    def list_objects(self, bucket_name: str, prefix: str = "") -> list[StorageObject]:
        raise NotImplementedError("GCP storage not fully implemented")
    
    def object_exists(self, bucket_name: str, key: str) -> bool:
        raise NotImplementedError("GCP storage not fully implemented")
    
    def get_object_metadata(self, bucket_name: str, key: str) -> StorageObject | None:
        raise NotImplementedError("GCP storage not fully implemented")
    
    def generate_presigned_url(self, bucket_name: str, key: str, expiration: int = 3600) -> str:
        raise NotImplementedError("GCP storage not fully implemented")


# Azure Implementation (placeholder)
class AzureStorage(CloudStorage):
    """Azure Blob Storage implementation."""
    
    def __init__(self, config: CloudConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from azure.storage.blob import BlobServiceClient
                self._client = BlobServiceClient.from_connection_string(
                    self.config.credentials.get('connection_string')
                )
            except ImportError:
                raise RuntimeError("azure-storage-blob not installed")
        return self._client
    
    def create_bucket(self, bucket_name: str, region: str = "") -> bool:
        raise NotImplementedError("Azure storage not fully implemented")
    
    def upload_file(self, bucket_name: str, key: str, data: bytes, 
                    content_type: str = "application/octet-stream") -> bool:
        raise NotImplementedError("Azure storage not fully implemented")
    
    def download_file(self, bucket_name: str, key: str) -> bytes:
        raise NotImplementedError("Azure storage not fully implemented")
    
    def delete_object(self, bucket_name: str, key: str) -> bool:
        raise NotImplementedError("Azure storage not fully implemented")
    
    def list_objects(self, bucket_name: str, prefix: str = "") -> list[StorageObject]:
        raise NotImplementedError("Azure storage not fully implemented")
    
    def object_exists(self, bucket_name: str, key: str) -> bool:
        raise NotImplementedError("Azure storage not fully implemented")
    
    def get_object_metadata(self, bucket_name: str, key: str) -> StorageObject | None:
        raise NotImplementedError("Azure storage not fully implemented")
    
    def generate_presigned_url(self, bucket_name: str, key: str, expiration: int = 3600) -> str:
        raise NotImplementedError("Azure storage not fully implemented")


# Factory functions
def create_storage(config: CloudConfig) -> CloudStorage:
    """Create storage client based on provider."""
    if config.provider == CloudProvider.AWS:
        return AWSStorage(config)
    elif config.provider == CloudProvider.GCP:
        return GCPStorage(config)
    elif config.provider == CloudProvider.AZURE:
        return AzureStorage(config)
    elif config.provider == CloudProvider.LOCAL:
        return LocalStorage()
    else:
        raise ValueError(f"Unsupported provider: {config.provider}")


def create_compute(config: CloudConfig) -> CloudCompute:
    """Create compute client based on provider."""
    if config.provider == CloudProvider.AWS:
        return AWSCompute(config)
    elif config.provider == CloudProvider.LOCAL:
        return LocalCompute()
    else:
        raise ValueError(f"Compute not implemented for provider: {config.provider}")


def create_batch(config: CloudConfig) -> CloudBatch:
    """Create batch client based on provider."""
    if config.provider == CloudProvider.AWS:
        return AWSBatch(config)
    elif config.provider == CloudProvider.LOCAL:
        return LocalBatch()
    else:
        raise ValueError(f"Batch not implemented for provider: {config.provider}")


# Cloud resource manager
class CloudResourceManager:
    """High-level cloud resource manager."""
    
    def __init__(self):
        self._configs: dict[CloudProvider, CloudConfig] = {}
        self._active_provider: CloudProvider | None = None
        self._storage_clients: dict[CloudProvider, CloudStorage] = {}
        self._compute_clients: dict[CloudProvider, CloudCompute] = {}
        self._batch_clients: dict[CloudProvider, CloudBatch] = {}
    
    def add_provider_config(self, config: CloudConfig) -> None:
        """Add a provider configuration."""
        self._configs[config.provider] = config
        # Create clients
        self._storage_clients[config.provider] = create_storage(config)
        self._compute_clients[config.provider] = create_compute(config)
        self._batch_clients[config.provider] = create_batch(config)
        # Set as active if none is set
        if self._active_provider is None:
            self._active_provider = config.provider
    
    def get_config(self) -> CloudConfig | None:
        """Get active provider config."""
        if self._active_provider and self._active_provider in self._configs:
            return self._configs[self._active_provider]
        # Return first config if no active provider set
        if self._configs:
            return next(iter(self._configs.values()))
        return None
    
    def set_active_provider(self, provider: CloudProvider) -> None:
        """Set active provider."""
        if provider not in self._configs:
            raise ValueError(f"Provider {provider} not configured")
        self._active_provider = provider
    
    def get_storage(self, provider: CloudProvider | None = None) -> CloudStorage:
        """Get storage client for provider."""
        provider = provider or self._active_provider
        if not provider or provider not in self._storage_clients:
            raise ValueError(f"No storage client for provider: {provider}")
        return self._storage_clients[provider]
    
    def get_compute(self, provider: CloudProvider | None = None) -> CloudCompute:
        """Get compute client for provider."""
        provider = provider or self._active_provider
        if not provider or provider not in self._compute_clients:
            raise ValueError(f"No compute client for provider: {provider}")
        return self._compute_clients[provider]
    
    def get_batch(self, provider: CloudProvider | None = None) -> CloudBatch:
        """Get batch client for provider."""
        provider = provider or self._active_provider
        if not provider or provider not in self._batch_clients:
            raise ValueError(f"No batch client for provider: {provider}")
        return self._batch_clients[provider]


# Global cloud manager
_cloud_manager: CloudResourceManager | None = None


def get_cloud_manager() -> CloudResourceManager:
    """Get global cloud resource manager."""
    global _cloud_manager
    if _cloud_manager is None:
        _cloud_manager = CloudResourceManager()
        # Add default local config
        _cloud_manager.add_provider_config(CloudConfig(provider=CloudProvider.LOCAL, region="local"))
        _cloud_manager.set_active_provider(CloudProvider.LOCAL)
    return _cloud_manager


def init_cloud(provider: CloudProvider = CloudProvider.LOCAL, region: str = "local", **kwargs) -> CloudResourceManager:
    """Initialize cloud integration."""
    global _cloud_manager
    config = CloudConfig(provider=provider, region=region, **kwargs)
    _cloud_manager = CloudResourceManager()
    _cloud_manager.add_provider_config(config)
    _cloud_manager.set_active_provider(provider)
    return _cloud_manager


# For backward compatibility with original API
class _LegacyStorageAPI:
    """Legacy storage API using BaseAPIClient pattern."""
    pass

# Module exports for backward compatibility
__all__ = [
    'CloudProvider',
    'StorageClass',
    'InstanceState',
    'JobStatus',
    'CloudConfig',
    'StorageObject',
    'ComputeInstance',
    'JobDefinition',
    'JobExecution',
    'CloudStorage',
    'CloudCompute',
    'CloudBatch',
    'AWSStorage',
    'AWSCompute',
    'AWSBatch',
    'LocalStorage',
    'LocalCompute',
    'LocalBatch',
    'GCPStorage',
    'AzureStorage',
    'create_storage',
    'create_compute',
    'create_batch',
    'CloudResourceManager',
    'get_cloud_manager',
    'init_cloud',
]