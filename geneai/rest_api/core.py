"""Advanced REST API - Phase 5.7 Core."""
from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional
from flask import Flask, request, jsonify, g

# Optional dependency
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    FLASK_LIMITER_AVAILABLE = True
except ImportError:
    Limiter = None
    get_remote_address = None
    FLASK_LIMITER_AVAILABLE = False

logger = logging.getLogger(__name__)


class APIVersion(Enum):
    """API versions."""
    V1 = "v1"


@dataclass
class APIKey:
    """API key for authentication."""
    key_id: str
    key_hash: str
    name: str
    user_id: str
    scopes: list[str] = field(default_factory=list)
    rate_limit: int = 1000  # requests per hour
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: str | None = None
    last_used: str | None = None
    is_active: bool = True
    
    def to_dict(self, include_hash: bool = False) -> dict[str, Any]:
        data = {
            "key_id": self.key_id,
            "name": self.name,
            "user_id": self.user_id,
            "scopes": self.scopes,
            "rate_limit": self.rate_limit,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_used": self.last_used,
            "is_active": self.is_active,
        }
        if include_hash:
            data["key_hash"] = self.key_hash
        return data


@dataclass
class APIResponse:
    """Standardized API response."""
    success: bool
    data: Any = None
    error: str | None = None
    error_code: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    
    def to_json(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "error_code": self.error_code,
            "meta": self.meta,
        }


class GeneAIAPI:
    """Main GeneAI REST API application."""
    
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.app = Flask(__name__)
        self.app.config['JSON_SORT_KEYS'] = False
        
        # Rate limiter (optional)
        if FLASK_LIMITER_AVAILABLE:
            self.limiter = Limiter(
                get_remote_address,
                app=self.app,
                default_limits=["1000 per hour"],
                storage_uri=self.config.get('rate_limit_storage', 'memory://'),
            )
        else:
            self.limiter = None
            logger.warning("flask-limiter not installed, rate limiting disabled")
        
        # API keys storage (in production, use database)
        self.api_keys: dict[str, APIKey] = {}
        
        # Register routes
        self._register_routes()
        self._register_error_handlers()
        self._register_middleware()
        
        # Initialize with demo key
        self._create_demo_key()
    
    def _create_demo_key(self) -> None:
        """Create a demo API key for testing."""
        key_id = "demo_key"
        raw_key = "geneai_demo_key_12345"
        import hashlib
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        
        demo_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            name="Demo Key",
            user_id="demo_user",
            scopes=["read", "write", "analyze"],
            rate_limit=10000,
        )
        self.api_keys[key_id] = demo_key
        logger.info("Created demo API key")
    
    def _register_middleware(self) -> None:
        """Register request/response middleware."""
        
        @self.app.before_request
        def before_request():
            g.start_time = time.time()
            g.request_id = secrets.token_urlsafe(8)
        
        @self.app.after_request
        def after_request(response):
            # Add headers
            response.headers['X-Request-ID'] = getattr(g, 'request_id', '')
            response.headers['X-API-Version'] = APIVersion.V1.value
            
            # Log request
            duration = time.time() - getattr(g, 'start_time', time.time())
            logger.info(
                f"{request.method} {request.path} - "
                f"{response.status_code} - {duration:.3f}s"
            )
            return response
    
    def _register_error_handlers(self) -> None:
        """Register error handlers."""
        
        @self.app.errorhandler(400)
        def bad_request(e):
            return jsonify(APIResponse(
                success=False,
                error="Bad request",
                error_code="BAD_REQUEST",
            ).to_json()), 400
        
        @self.app.errorhandler(401)
        def unauthorized(e):
            return jsonify(APIResponse(
                success=False,
                error="Unauthorized",
                error_code="UNAUTHORIZED",
            ).to_json()), 401
        
        @self.app.errorhandler(403)
        def forbidden(e):
            return jsonify(APIResponse(
                success=False,
                error="Forbidden",
                error_code="FORBIDDEN",
            ).to_json()), 403
        
        @self.app.errorhandler(404)
        def not_found(e):
            return jsonify(APIResponse(
                success=False,
                error="Not found",
                error_code="NOT_FOUND",
            ).to_json()), 404
        
        @self.app.errorhandler(429)
        def rate_limit(e):
            return jsonify(APIResponse(
                success=False,
                error="Rate limit exceeded",
                error_code="RATE_LIMITED",
            ).to_json()), 429
        
        @self.app.errorhandler(500)
        def internal_error(e):
            logger.error(f"Internal error: {e}")
            return jsonify(APIResponse(
                success=False,
                error="Internal server error",
                error_code="INTERNAL_ERROR",
            ).to_json()), 500
    
    def _register_routes(self) -> None:
        """Register API routes."""
        
        # Health check
        @self.app.route('/health', methods=['GET'])
        def health():
            return jsonify(APIResponse(
                success=True,
                data={"status": "healthy", "version": APIVersion.V1.value},
            ).to_json())
        
        @self.app.route('/ready', methods=['GET'])
        def ready():
            # Readiness check - verify DB connections, API connectivity
            checks = {
                "api": "ok",
                "knowledge_graph": "unknown",
                "databases": "unknown",
            }
            
            # Check knowledge graph
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                stats = kq.get_database_stats()
                checks["knowledge_graph"] = "ok" if stats else "degraded"
                checks["databases"] = "ok"
            except Exception as e:
                logger.warning(f"Readiness check failed: {e}")
                checks["knowledge_graph"] = "failed"
                checks["databases"] = "failed"
            
            all_ok = all(v == "ok" for v in checks.values())
            
            return jsonify(APIResponse(
                success=all_ok,
                data={
                    "status": "ready" if all_ok else "not_ready",
                    "checks": checks,
                    "version": APIVersion.V1.value,
                },
            ).to_json()), 200 if all_ok else 503
        
        @self.app.route('/api/v1/info', methods=['GET'])
        def api_info():
            return jsonify(APIResponse(
                success=True,
                data={
                    "name": "GeneAI Research API",
                    "version": APIVersion.V1.value,
                    "description": "REST API for biotechnology research",
                    "endpoints": {
                        "sequence": "/api/v1/sequence",
                        "variants": "/api/v1/variants",
                        "genes": "/api/v1/genes",
                        "diseases": "/api/v1/diseases",
                        "proteins": "/api/v1/proteins",
                        "drugs": "/api/v1/drugs",
                        "pathways": "/api/v1/pathways",
                        "literature": "/api/v1/literature",
                        "analysis": "/api/v1/analysis",
                        "workflows": "/api/v1/workflows",
                        "knowledge": "/api/v1/knowledge",
                    },
                },
            ).to_json())
        
        # API Key management
        @self.app.route('/api/v1/auth/keys', methods=['GET'])
        @self.require_auth(scopes=['admin'])
        def list_keys():
            keys = [k.to_dict() for k in self.api_keys.values() if k.is_active]
            return jsonify(APIResponse(success=True, data=keys).to_json())
        
        @self.app.route('/api/v1/auth/keys', methods=['POST'])
        @self.require_auth(scopes=['admin'])
        def create_key():
            data = request.get_json() or {}
            name = data.get('name', 'Unnamed Key')
            scopes = data.get('scopes', ['read'])
            rate_limit = data.get('rate_limit', 1000)
            expires_days = data.get('expires_days')
            
            key_id = secrets.token_urlsafe(16)
            raw_key = f"geneai_{secrets.token_urlsafe(32)}"
            import hashlib
            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            
            expires_at = None
            if expires_days:
                expires_at = (datetime.now() + timedelta(days=expires_days)).isoformat()
            
            api_key = APIKey(
                key_id=key_id,
                key_hash=key_hash,
                name=name,
                user_id=getattr(g, 'user_id', 'unknown'),
                scopes=scopes,
                rate_limit=rate_limit,
                expires_at=expires_at,
            )
            self.api_keys[key_id] = api_key
            
            return jsonify(APIResponse(
                success=True,
                data={
                    "key_id": key_id,
                    "api_key": raw_key,  # Only shown once!
                    "name": name,
                    "scopes": scopes,
                    "rate_limit": rate_limit,
                    "expires_at": expires_at,
                },
                meta={"warning": "Store this key securely. It will not be shown again."}
            ).to_json()), 201
        
        @self.app.route('/api/v1/auth/keys/<key_id>', methods=['DELETE'])
        @self.require_auth(scopes=['admin'])
        def revoke_key(key_id):
            if key_id in self.api_keys:
                self.api_keys[key_id].is_active = False
                return jsonify(APIResponse(success=True, data={"revoked": True}).to_json())
            return jsonify(APIResponse(
                success=False, error="Key not found", error_code="NOT_FOUND"
            ).to_json()), 404
        
        # Sequence analysis
        @self.app.route('/api/v1/sequence/analyze', methods=['POST'])
        @self.require_auth(scopes=['read', 'analyze'])
        @self.limiter.limit("100 per minute")
        def analyze_sequence():
            data = request.get_json() or {}
            sequence = data.get('sequence', '')
            seq_type = data.get('type', 'DNA')
            
            if not sequence:
                return jsonify(APIResponse(
                    success=False, error="Sequence required", error_code="MISSING_SEQUENCE"
                ).to_json()), 400
            
            try:
                from geneai.sequence import analyze_sequence
                result = analyze_sequence(sequence, seq_type)
                return jsonify(APIResponse(success=True, data=result).to_json())
            except Exception as e:
                logger.error(f"Sequence analysis failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="ANALYSIS_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/sequence/parse', methods=['POST'])
        @self.require_auth(scopes=['read', 'analyze'])
        @self.limiter.limit("50 per minute")
        def parse_sequence():
            if 'file' not in request.files:
                return jsonify(APIResponse(
                    success=False, error="No file provided", error_code="NO_FILE"
                ).to_json()), 400
            
            file = request.files['file']
            seq_type = request.form.get('type', 'DNA')
            
            try:
                from geneai.sequence import parse_sequence_file
                content = file.read()
                records = parse_sequence_file(content, file.filename)
                
                results = []
                for record in records:
                    from geneai.sequence import analyze_sequence
                    result = analyze_sequence(record['sequence'], seq_type)
                    result['record_id'] = record['id']
                    results.append(result)
                
                return jsonify(APIResponse(success=True, data=results).to_json())
            except Exception as e:
                logger.error(f"Sequence parsing failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="PARSE_FAILED"
                ).to_json()), 500
        
        # Variant analysis
        @self.app.route('/api/v1/variants/parse', methods=['POST'])
        @self.require_auth(scopes=['read', 'analyze'])
        @self.limiter.limit("20 per minute")
        def parse_variants():
            if 'file' not in request.files:
                return jsonify(APIResponse(
                    success=False, error="No VCF file provided", error_code="NO_FILE"
                ).to_json()), 400
            
            file = request.files['file']
            
            try:
                from geneai.variants import parse_vcf, summarize_vcf_stream
                content = file.read()
                
                if len(content) > 50 * 1024 * 1024:  # 50MB
                    summary, meta, preview = summarize_vcf_stream(
                        type('obj', (object,), {'getvalue': lambda self: content, 'name': file.filename})(),
                        file.filename
                    )
                    return jsonify(APIResponse(success=True, data={
                        "mode": "streaming",
                        "summary": summary,
                        "meta": meta,
                        "preview": preview[:1000],
                    }).to_json())
                else:
                    variants, meta = parse_vcf(content, file.filename)
                    return jsonify(APIResponse(success=True, data={
                        "mode": "full",
                        "variants": variants[:10000],  # Limit response
                        "meta": meta,
                        "total": len(variants),
                    }).to_json())
            except Exception as e:
                logger.error(f"VCF parsing failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="PARSE_FAILED"
                ).to_json()), 500
        
        # Gene analysis
        @self.app.route('/api/v1/genes/search', methods=['GET'])
        @self.require_auth(scopes=['read'])
        @self.limiter.limit("200 per minute")
        def search_genes():
            query = request.args.get('q', '')
            limit = min(int(request.args.get('limit', 20)), 100)
            
            if not query:
                return jsonify(APIResponse(
                    success=False, error="Query required", error_code="MISSING_QUERY"
                ).to_json()), 400
            
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                result = kq.search_genes(query, limit)
                return jsonify(APIResponse(success=True, data=result.data).to_json())
            except Exception as e:
                logger.error(f"Gene search failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="SEARCH_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/genes/<symbol>', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def get_gene(symbol):
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                gene = kq.get_gene(symbol.upper())
                
                if not gene:
                    return jsonify(APIResponse(
                        success=False, error="Gene not found", error_code="NOT_FOUND"
                    ).to_json()), 404
                
                # Get related data
                diseases = kq.get_gene_diseases(symbol.upper())
                pathways = kq.get_gene_pathways(symbol.upper())
                proteins = kq.get_gene_proteins(symbol.upper())
                variants = kq.get_gene_variants(symbol.upper(), 50)
                
                return jsonify(APIResponse(success=True, data={
                    "gene": gene,
                    "diseases": diseases.data,
                    "pathways": pathways.data,
                    "proteins": proteins.data,
                    "variants": variants.data,
                }).to_json())
            except Exception as e:
                logger.error(f"Gene lookup failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="LOOKUP_FAILED"
                ).to_json()), 500
        
        # Disease analysis
        @self.app.route('/api/v1/diseases/search', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def search_diseases():
            query = request.args.get('q', '')
            limit = min(int(request.args.get('limit', 20)), 100)
            
            if not query:
                return jsonify(APIResponse(
                    success=False, error="Query required", error_code="MISSING_QUERY"
                ).to_json()), 400
            
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                result = kq.search_diseases(query, limit)
                return jsonify(APIResponse(success=True, data=result.data).to_json())
            except Exception as e:
                logger.error(f"Disease search failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="SEARCH_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/diseases/<name>/genes', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def disease_genes(name):
            limit = min(int(request.args.get('limit', 50)), 200)
            
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                result = kq.get_disease_genes(name, limit)
                return jsonify(APIResponse(success=True, data=result.data).to_json())
            except Exception as e:
                logger.error(f"Disease genes failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="ANALYSIS_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/diseases/<name>/drugs', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def disease_drugs(name):
            limit = min(int(request.args.get('limit', 50)), 200)
            
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                result = kq.get_disease_drugs(name, limit)
                return jsonify(APIResponse(success=True, data=result.data).to_json())
            except Exception as e:
                logger.error(f"Disease drugs failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="ANALYSIS_FAILED"
                ).to_json()), 500
        
        # Drug search
        @self.app.route('/api/v1/drugs/search', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def search_drugs():
            query = request.args.get('q', '')
            limit = min(int(request.args.get('limit', 20)), 100)
            
            if not query:
                return jsonify(APIResponse(
                    success=False, error="Query required", error_code="MISSING_QUERY"
                ).to_json()), 400
            
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                result = kq.search_drugs(query, limit)
                return jsonify(APIResponse(success=True, data=result.data).to_json())
            except Exception as e:
                logger.error(f"Drug search failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="SEARCH_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/drugs/<identifier>', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def get_drug(identifier):
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                drug = kq.get_drug(chembl_id=identifier) or kq.get_drug(name=identifier)
                
                if not drug:
                    return jsonify(APIResponse(
                        success=False, error="Drug not found", error_code="NOT_FOUND"
                    ).to_json()), 404
                
                targets = kq.get_drug_targets(drug['chembl_id'])
                
                return jsonify(APIResponse(success=True, data={
                    "drug": drug,
                    "targets": targets.data,
                }).to_json())
            except Exception as e:
                logger.error(f"Drug lookup failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="LOOKUP_FAILED"
                ).to_json()), 500
        
        # Protein analysis
        @self.app.route('/api/v1/proteins/search', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def search_proteins():
            query = request.args.get('q', '')
            limit = min(int(request.args.get('limit', 20)), 100)
            
            if not query:
                return jsonify(APIResponse(
                    success=False, error="Query required", error_code="MISSING_QUERY"
                ).to_json()), 400
            
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                result = kq.search_proteins(query, limit)
                return jsonify(APIResponse(success=True, data=result.data).to_json())
            except Exception as e:
                logger.error(f"Protein search failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="SEARCH_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/proteins/<uniprot_id>', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def get_protein(uniprot_id):
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                protein = kq.get_protein(uniprot_id)
                
                if not protein:
                    return jsonify(APIResponse(
                        success=False, error="Protein not found", error_code="NOT_FOUND"
                    ).to_json()), 404
                
                interactions = kq.get_protein_interactions(uniprot_id, 50)
                
                return jsonify(APIResponse(success=True, data={
                    "protein": protein,
                    "interactions": interactions.data,
                }).to_json())
            except Exception as e:
                logger.error(f"Protein lookup failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="LOOKUP_FAILED"
                ).to_json()), 500
        
        # Pathway analysis
        @self.app.route('/api/v1/pathways/search', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def search_pathways():
            query = request.args.get('q', '')
            limit = min(int(request.args.get('limit', 20)), 100)
            
            if not query:
                return jsonify(APIResponse(
                    success=False, error="Query required", error_code="MISSING_QUERY"
                ).to_json()), 400
            
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                result = kq.search_pathways(query, limit)
                return jsonify(APIResponse(success=True, data=result.data).to_json())
            except Exception as e:
                logger.error(f"Pathway search failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="SEARCH_FAILED"
                ).to_json()), 500
        
        # Literature search
        @self.app.route('/api/v1/literature/search', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def search_literature():
            query = request.args.get('q', '')
            limit = min(int(request.args.get('limit', 20)), 100)
            
            if not query:
                return jsonify(APIResponse(
                    success=False, error="Query required", error_code="MISSING_QUERY"
                ).to_json()), 400
            
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                result = kq.search_literature(query, limit)
                return jsonify(APIResponse(success=True, data=result.data).to_json())
            except Exception as e:
                logger.error(f"Literature search failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="SEARCH_FAILED"
                ).to_json()), 500
        
        # Analysis endpoints
        @self.app.route('/api/v1/analysis/admet', methods=['POST'])
        @self.require_auth(scopes=['read', 'analyze'])
        @self.limiter.limit("50 per minute")
        def predict_admet():
            data = request.get_json() or {}
            smiles = data.get('smiles', '')
            
            if not smiles:
                return jsonify(APIResponse(
                    success=False, error="SMILES required", error_code="MISSING_SMILES"
                ).to_json()), 400
            
            try:
                from geneai.admet_prediction import predict_admet
                result = predict_admet(smiles)
                return jsonify(APIResponse(success=True, data=result).to_json())
            except Exception as e:
                logger.error(f"ADMET prediction failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="PREDICTION_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/analysis/drug-target', methods=['POST'])
        @self.require_auth(scopes=['read', 'analyze'])
        @self.limiter.limit("30 per minute")
        def predict_drug_target():
            data = request.get_json() or {}
            smiles = data.get('smiles', '')
            target = data.get('target', '')
            
            if not smiles or not target:
                return jsonify(APIResponse(
                    success=False, error="SMILES and target required", error_code="MISSING_PARAMS"
                ).to_json()), 400
            
            try:
                from geneai.drug_target_prediction import predict_drug_target_interactions
                result = predict_drug_target_interactions(smiles, target)
                return jsonify(APIResponse(success=True, data=result).to_json())
            except Exception as e:
                logger.error(f"Drug-target prediction failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="PREDICTION_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/analysis/repurposing', methods=['POST'])
        @self.require_auth(scopes=['read', 'analyze'])
        @self.limiter.limit("20 per minute")
        def find_repurposing():
            data = request.get_json() or {}
            disease = data.get('disease', '')
            target = data.get('target', '')
            limit = min(data.get('limit', 20), 100)
            
            if not disease:
                return jsonify(APIResponse(
                    success=False, error="Disease required", error_code="MISSING_DISEASE"
                ).to_json()), 400
            
            try:
                from geneai.drug_repurposing import find_repurposing_candidates
                result = find_repurposing_candidates(disease, target, limit)
                return jsonify(APIResponse(success=True, data=result).to_json())
            except Exception as e:
                logger.error(f"Repurposing failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="ANALYSIS_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/analysis/biomarker', methods=['POST'])
        @self.require_auth(scopes=['read', 'analyze'])
        @self.limiter.limit("10 per minute")
        def discover_biomarkers():
            data = request.get_json() or {}
            disease = data.get('disease', '')
            sample_type = data.get('sample_type', 'blood')
            data_source = data.get('data_source', 'public')
            
            if not disease:
                return jsonify(APIResponse(
                    success=False, error="Disease required", error_code="MISSING_DISEASE"
                ).to_json()), 400
            
            try:
                from geneai.biomarker_discovery import run_biomarker_discovery
                result = run_biomarker_discovery(disease, sample_type, data_source)
                return jsonify(APIResponse(success=True, data=result.__dict__ if hasattr(result, '__dict__') else str(result)).to_json())
            except Exception as e:
                logger.error(f"Biomarker discovery failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="ANALYSIS_FAILED"
                ).to_json()), 500
        
        # Workflow endpoints
        @self.app.route('/api/v1/workflows/precision', methods=['POST'])
        @self.require_auth(scopes=['read', 'analyze'])
        @self.limiter.limit("5 per minute")
        def run_precision_workflow():
            data = request.get_json() or {}
            disease = data.get('disease', '')
            gene_symbols = data.get('gene_symbols', [])
            mutations = data.get('mutations', [])
            
            if not disease:
                return jsonify(APIResponse(
                    success=False, error="Disease required", error_code="MISSING_DISEASE"
                ).to_json()), 400
            
            try:
                from geneai.integrated_precision import run_integrated_precision_drug_discovery
                result = run_integrated_precision_drug_discovery(disease, gene_symbols, mutations)
                return jsonify(APIResponse(success=True, data=result.__dict__ if hasattr(result, '__dict__') else str(result)).to_json())
            except Exception as e:
                logger.error(f"Precision workflow failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="WORKFLOW_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/workflows/mutation-to-drug', methods=['POST'])
        @self.require_auth(scopes=['read', 'analyze'])
        @self.limiter.limit("5 per minute")
        def run_mutation_workflow():
            data = request.get_json() or {}
            mutations = data.get('mutations', [])
            disease = data.get('disease', '')
            
            if not mutations:
                return jsonify(APIResponse(
                    success=False, error="Mutations required", error_code="MISSING_MUTATIONS"
                ).to_json()), 400
            
            try:
                from geneai.ai_research_intelligence.mutation_to_drug_workflow import run_mutation_to_drug_workflow
                result = run_mutation_to_drug_workflow(mutations, disease)
                return jsonify(APIResponse(success=True, data=result.__dict__ if hasattr(result, '__dict__') else str(result)).to_json())
            except Exception as e:
                logger.error(f"Mutation workflow failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="WORKFLOW_FAILED"
                ).to_json()), 500
        
        # Knowledge graph queries
        @self.app.route('/api/v1/knowledge/query', methods=['POST'])
        @self.require_auth(scopes=['read'])
        @self.limiter.limit("100 per minute")
        def knowledge_query():
            data = request.get_json() or {}
            query_type = data.get('type', '')
            params = data.get('params', {})
            
            try:
                from geneai.unified_knowledge import get_knowledge_query
                kq = get_knowledge_query()
                
                if query_type == 'gene_network':
                    result = kq.get_gene_network(params.get('gene', ''), params.get('depth', 1))
                elif query_type == 'drug_target_disease':
                    result = kq.get_drug_target_disease_path(params.get('drug', ''), params.get('disease', ''))
                elif query_type == 'stats':
                    result = kq.get_database_stats()
                else:
                    return jsonify(APIResponse(
                        success=False, error="Unknown query type", error_code="INVALID_QUERY_TYPE"
                    ).to_json()), 400
                
                return jsonify(APIResponse(success=True, data=result).to_json())
            except Exception as e:
                logger.error(f"Knowledge query failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="QUERY_FAILED"
                ).to_json()), 500
        
        # AI Assistant
        @self.app.route('/api/v1/assistant/ask', methods=['POST'])
        @self.require_auth(scopes=['read', 'analyze'])
        @self.limiter.limit("30 per minute")
        def ask_assistant():
            data = request.get_json() or {}
            question = data.get('question', '')
            session_id = data.get('session_id')
            
            if not question:
                return jsonify(APIResponse(
                    success=False, error="Question required", error_code="MISSING_QUESTION"
                ).to_json()), 400
            
            try:
                from geneai.biotech_assistant import create_biotech_assistant
                assistant = create_biotech_assistant()
                
                if session_id:
                    # Restore session context would go here
                    pass
                
                answer = assistant.ask(question)
                
                return jsonify(APIResponse(success=True, data={
                    "answer": answer.answer_text,
                    "confidence": answer.confidence,
                    "question_type": answer.question_type.value,
                    "citations": [c.to_dict() for c in answer.citations],
                    "follow_up_questions": answer.follow_up_questions,
                    "limitations": answer.limitations,
                    "session_id": session_id or assistant.session_id,
                }).to_json())
            except Exception as e:
                logger.error(f"Assistant query failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="ASSISTANT_FAILED"
                ).to_json()), 500
        
        # Automation
        @self.app.route('/api/v1/automation/tasks', methods=['GET'])
        @self.require_auth(scopes=['read'])
        def list_automation_tasks():
            try:
                from geneai.research_automation import get_automation_engine
                engine = get_automation_engine()
                tasks = engine.list_tasks()
                return jsonify(APIResponse(success=True, data=[t.to_dict() for t in tasks]).to_json())
            except Exception as e:
                logger.error(f"List automation tasks failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="LIST_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/automation/tasks', methods=['POST'])
        @self.require_auth(scopes=['read', 'write'])
        def create_automation_task():
            data = request.get_json() or {}
            
            try:
                from geneai.research_automation import get_automation_engine, TriggerType
                engine = get_automation_engine()
                
                task = engine.create_task(
                    name=data.get('name', 'Untitled Task'),
                    description=data.get('description', ''),
                    trigger_type=TriggerType(data.get('trigger_type', 'manual')),
                    schedule=data.get('schedule', ''),
                    steps=data.get('steps', []),
                )
                
                return jsonify(APIResponse(success=True, data=task.to_dict()).to_json()), 201
            except Exception as e:
                logger.error(f"Create automation task failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="CREATE_FAILED"
                ).to_json()), 500
        
        @self.app.route('/api/v1/automation/tasks/<task_id>/run', methods=['POST'])
        @self.require_auth(scopes=['read', 'write'])
        def run_automation_task(task_id):
            data = request.get_json() or {}
            
            try:
                from geneai.research_automation import get_automation_engine
                engine = get_automation_engine()
                execution = engine.execute_task(task_id, data.get('context'))
                
                return jsonify(APIResponse(success=True, data=execution.to_dict()).to_json())
            except Exception as e:
                logger.error(f"Run automation task failed: {e}")
                return jsonify(APIResponse(
                    success=False, error=str(e), error_code="EXECUTION_FAILED"
                ).to_json()), 500
    
    def require_auth(self, scopes: list[str] = None):
        """Decorator for requiring authentication."""
        def decorator(f: Callable):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                # Check API key
                auth_header = request.headers.get('Authorization', '')
                if not auth_header.startswith('Bearer '):
                    return jsonify(APIResponse(
                        success=False, error="Missing or invalid Authorization header",
                        error_code="MISSING_AUTH"
                    ).to_json()), 401
                
                api_key = auth_header[7:]  # Remove 'Bearer '
                import hashlib
                key_hash = hashlib.sha256(api_key.encode()).hexdigest()
                
                # Find matching key
                matched_key = None
                for key in self.api_keys.values():
                    if key.is_active and key.key_hash == key_hash:
                        if key.expires_at and datetime.now() > datetime.fromisoformat(key.expires_at):
                            continue
                        matched_key = key
                        break
                
                if not matched_key:
                    return jsonify(APIResponse(
                        success=False, error="Invalid API key", error_code="INVALID_KEY"
                    ).to_json()), 401
                
                # Check scopes
                if scopes:
                    if not any(scope in matched_key.scopes for scope in scopes):
                        return jsonify(APIResponse(
                            success=False, error="Insufficient scopes", error_code="INSUFFICIENT_SCOPE"
                        ).to_json()), 403
                
                # Update last used
                matched_key.last_used = datetime.now().isoformat()
                
                # Set user context
                g.user_id = matched_key.user_id
                g.api_key_id = matched_key.key_id
                g.scopes = matched_key.scopes
                
                return f(*args, **kwargs)
            return decorated_function
        return decorator
    
    def run(self, host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
        """Run the API server."""
        self.app.run(host=host, port=port, debug=debug)


# Global API instance
_api_instance: GeneAIAPI | None = None


def get_api(config: dict[str, Any] | None = None) -> GeneAIAPI:
    """Get global API instance."""
    global _api_instance
    if _api_instance is None:
        _api_instance = GeneAIAPI(config)
    return _api_instance


def create_api(config: dict[str, Any] | None = None) -> GeneAIAPI:
    """Create new API instance."""
    global _api_instance
    _api_instance = GeneAIAPI(config)
    return _api_instance