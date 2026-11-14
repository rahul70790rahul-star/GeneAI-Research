"""GeneAI Research - Production Configuration for Streamlit Community Cloud.

This module provides configuration management for both local development
and Streamlit Community Cloud deployment.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class DatabaseConfig:
    """Database configuration supporting both SQLite and PostgreSQL."""
    
    # SQLite (local development)
    sqlite_path: str = "data/geneai_lab.sqlite3"
    
    # PostgreSQL (production - Neon)
    postgres_url: Optional[str] = None
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800
    
    @property
    def is_postgres(self) -> bool:
        return self.postgres_url is not None and self.postgres_url.startswith("postgresql")
    
    @property
    def connection_string(self) -> str:
        if self.is_postgres:
            return self.postgres_url
        return f"sqlite:///{self.sqlite_path}"


@dataclass
class RedisConfig:
    """Redis configuration supporting both local and Upstash."""
    
    # Standard Redis (local/Docker)
    redis_url: Optional[str] = None
    
    # Upstash REST API (serverless)
    upstash_rest_url: Optional[str] = None
    upstash_rest_token: Optional[str] = None
    
    @property
    def is_upstash(self) -> bool:
        return self.upstash_rest_url is not None and self.upstash_rest_token is not None
    
    @property
    def is_configured(self) -> bool:
        return self.is_upstash or self.redis_url is not None


@dataclass
class SecurityConfig:
    """Security configuration."""
    
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    encryption_key: str = ""
    api_key_prefix: str = "gai_"
    
    def validate(self) -> list[str]:
        """Validate security configuration."""
        issues = []
        if not self.secret_key or len(self.secret_key) < 32:
            issues.append("SECRET_KEY must be at least 32 characters")
        if not self.encryption_key:
            issues.append("ENCRYPTION_KEY is required")
        return issues


@dataclass
class ExternalAPIConfig:
    """External API keys configuration."""
    
    ncbi_api_key: str = ""
    uniprot_api_key: str = ""
    opentargets_api_key: str = ""
    alphafold_api_key: str = ""
    chemlb_api_key: str = ""
    
    def apply_to_env(self) -> None:
        """Apply API keys to environment variables."""
        if self.ncbi_api_key:
            os.environ["NCBI_API_KEY"] = self.ncbi_api_key
        if self.uniprot_api_key:
            os.environ["UNIPROT_API_KEY"] = self.uniprot_api_key
        if self.opentargets_api_key:
            os.environ["OPENTARGETS_API_KEY"] = self.opentargets_api_key
        if self.alphafold_api_key:
            os.environ["ALPHAFOLD_API_KEY"] = self.alphafold_api_key
        if self.chemlb_api_key:
            os.environ["CHEMLB_API_KEY"] = self.chemlb_api_key


@dataclass
class FeatureFlags:
    """Feature flags for enabling/disabling functionality."""
    
    enable_multi_user: bool = True
    enable_rest_api: bool = True
    enable_cloud_integration: bool = False
    enable_advanced_analytics: bool = True
    enable_audit_logging: bool = True
    enable_mutation_ml: bool = True


@dataclass
class MLConfig:
    """ML model configuration."""
    
    model_dir: str = "data/models"
    default_model: str = "best_mutation_model_real.pkl"
    enable_shap: bool = True


@dataclass
class AppConfig:
    """Main application configuration."""
    
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    
    # API Configuration
    api_base_url: str = "http://localhost:8000"
    cors_origins: list[str] = field(default_factory=lambda: [
        "http://localhost:8501",
        "http://localhost:8502",
        "http://localhost:8000",
    ])
    
    # Streamlit Configuration
    server_port: int = 8501
    server_address: str = "0.0.0.0"
    server_headless: bool = True
    
    # Sub-configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    external_apis: ExternalAPIConfig = field(default_factory=ExternalAPIConfig)
    features: FeatureFlags = field(default_factory=FeatureFlags)
    ml: MLConfig = field(default_factory=MLConfig)
    performance: dict = field(default_factory=lambda: {
        "cache_ttl_seconds": 300,
        "max_concurrent_jobs": 5,
        "worker_processes": 2,
    })


# Global configuration instance
_config: Optional[AppConfig] = None


def load_config() -> AppConfig:
    """Load configuration from environment variables and Streamlit secrets."""
    global _config
    
    if _config is not None:
        return _config
    
    config = AppConfig()
    
    # Environment
    config.environment = os.getenv("GENEAI_ENV", os.getenv("ENVIRONMENT", "development"))
    config.debug = os.getenv("DEBUG", "false").lower() == "true"
    config.log_level = os.getenv("LOG_LEVEL", "INFO")
    
    # API Configuration
    config.api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    cors_origins = os.getenv("CORS_ORIGINS", "")
    if cors_origins:
        config.cors_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    
    # Streamlit Configuration
    config.server_port = int(os.getenv("STREAMLIT_SERVER_PORT", "8501"))
    config.server_address = os.getenv("STREAMLIT_SERVER_ADDRESS", "0.0.0.0")
    config.server_headless = os.getenv("STREAMLIT_SERVER_HEADLESS", "true").lower() == "true"
    
    # Database Configuration
    config.database.postgres_url = os.getenv("DATABASE_URL") or os.getenv("GENEAI_DATABASE_PATH")
    config.database.sqlite_path = os.getenv("GENEAI_SQLITE_PATH", "data/geneai_lab.sqlite3")
    config.database.pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
    config.database.max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    
    # Redis Configuration
    redis_url = os.getenv("REDIS_URL", "").strip()
    config.redis.redis_url = redis_url if redis_url else None
    upstash_url = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
    config.redis.upstash_rest_url = upstash_url if upstash_url else None
    upstash_token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
    config.redis.upstash_rest_token = upstash_token if upstash_token else None
    
    # Security Configuration
    config.security.secret_key = os.getenv("SECRET_KEY", "")
    config.security.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    config.security.jwt_expiration_hours = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
    config.security.encryption_key = os.getenv("ENCRYPTION_KEY", "")
    config.security.api_key_prefix = os.getenv("API_KEY_PREFIX", "gai_")
    
    # External APIs
    config.external_apis.ncbi_api_key = os.getenv("NCBI_API_KEY", "")
    config.external_apis.uniprot_api_key = os.getenv("UNIPROT_API_KEY", "")
    config.external_apis.opentargets_api_key = os.getenv("OPENTARGETS_API_KEY", "")
    config.external_apis.alphafold_api_key = os.getenv("ALPHAFOLD_API_KEY", "")
    config.external_apis.chemlb_api_key = os.getenv("CHEMLB_API_KEY", "")
    
    # Feature Flags
    config.features.enable_multi_user = os.getenv("ENABLE_MULTI_USER", "true").lower() == "true"
    config.features.enable_rest_api = os.getenv("ENABLE_REST_API", "true").lower() == "true"
    config.features.enable_cloud_integration = os.getenv("ENABLE_CLOUD_INTEGRATION", "false").lower() == "true"
    config.features.enable_advanced_analytics = os.getenv("ENABLE_ADVANCED_ANALYTICS", "true").lower() == "true"
    config.features.enable_audit_logging = os.getenv("ENABLE_AUDIT_LOGGING", "true").lower() == "true"
    config.features.enable_mutation_ml = os.getenv("ENABLE_MUTATION_ML", "true").lower() == "true"
    
    # ML Configuration
    config.ml.model_dir = os.getenv("MODEL_DIR", "data/models")
    config.ml.default_model = os.getenv("DEFAULT_MODEL", "best_mutation_model_real.pkl")
    config.ml.enable_shap = os.getenv("ENABLE_SHAP", "true").lower() == "true"
    
    # Performance
    config.performance["cache_ttl_seconds"] = int(os.getenv("CACHE_TTL_SECONDS", "300"))
    config.performance["max_concurrent_jobs"] = int(os.getenv("MAX_CONCURRENT_JOBS", "5"))
    config.performance["worker_processes"] = int(os.getenv("WORKER_PROCESSES", "2"))
    
    # Try to load from Streamlit secrets (if running on Streamlit Cloud)
    try:
        import streamlit as st
        if hasattr(st, 'secrets'):
            # Database
            if 'database' in st.secrets:
                db_secrets = st.secrets['database']
                if 'url' in db_secrets:
                    config.database.postgres_url = db_secrets['url']
                if 'pool_size' in db_secrets:
                    config.database.pool_size = int(db_secrets['pool_size'])
            
            # Redis
            if 'redis' in st.secrets:
                redis_secrets = st.secrets['redis']
                if 'url' in redis_secrets and redis_secrets['url']:
                    config.redis.upstash_rest_url = redis_secrets['url'].strip() if redis_secrets['url'].strip() else None
                if 'token' in redis_secrets and redis_secrets['token']:
                    config.redis.upstash_rest_token = redis_secrets['token'].strip() if redis_secrets['token'].strip() else None
            
            # Security
            if 'security' in st.secrets:
                sec_secrets = st.secrets['security']
                if 'secret_key' in sec_secrets:
                    config.security.secret_key = sec_secrets['secret_key']
                if 'encryption_key' in sec_secrets:
                    config.security.encryption_key = sec_secrets['encryption_key']
            
            # External APIs
            if 'external_apis' in st.secrets:
                api_secrets = st.secrets['external_apis']
                for key in ['ncbi_api_key', 'uniprot_api_key', 'opentargets_api_key', 
                           'alphafold_api_key', 'chemlb_api_key']:
                    if key in api_secrets:
                        setattr(config.external_apis, key, api_secrets[key])
            
            # Features
            if 'features' in st.secrets:
                feat_secrets = st.secrets['features']
                for key in ['enable_multi_user', 'enable_rest_api', 'enable_cloud_integration',
                           'enable_advanced_analytics', 'enable_audit_logging', 'enable_mutation_ml']:
                    if key in feat_secrets:
                        setattr(config.features, key, bool(feat_secrets[key]))
            
            # ML
            if 'ml_models' in st.secrets:
                ml_secrets = st.secrets['ml_models']
                if 'model_dir' in ml_secrets:
                    config.ml.model_dir = ml_secrets['model_dir']
                if 'default_model' in ml_secrets:
                    config.ml.default_model = ml_secrets['default_model']
                if 'enable_shap' in ml_secrets:
                    config.ml.enable_shap = bool(ml_secrets['enable_shap'])
            
            # App
            if 'app' in st.secrets:
                app_secrets = st.secrets['app']
                if 'api_base_url' in app_secrets:
                    config.api_base_url = app_secrets['api_base_url']
    except Exception:
        # Streamlit not available or secrets not configured
        pass
    
    # Apply external API keys to environment
    config.external_apis.apply_to_env()
    
    _config = config
    return config


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    if _config is None:
        return load_config()
    return _config


def reset_config() -> None:
    """Reset configuration (useful for testing)."""
    global _config
    _config = None


# Convenience functions
def is_production() -> bool:
    """Check if running in production environment."""
    return get_config().environment == "production"


def is_streamlit_cloud() -> bool:
    """Check if running on Streamlit Community Cloud."""
    return "STREAMLIT_SHARING" in os.environ or "STREAMLIT_CLOUD" in os.environ


def get_database_url() -> str:
    """Get the database connection URL."""
    return get_config().database.connection_string


def get_redis_config() -> RedisConfig:
    """Get Redis configuration."""
    return get_config().redis


# Initialize on import
load_config()