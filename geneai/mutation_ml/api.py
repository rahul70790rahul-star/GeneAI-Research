"""FastAPI endpoints for mutation ML pipeline."""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from geneai.mutation_ml.integration import MutationMLIntegration, enhance_vcf_with_ml
from geneai.mutation_ml.training import MutationMLTrainer, TrainingResult, train_mutation_classifier
from geneai.mutation_ml.explainability import MutationExplainer, explain_prediction
from geneai.mutation import summarize_vcf_interpretation_stream

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="GeneAI Mutation ML API",
    description="ML training and prediction API for variant pathogenicity interpretation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class VariantInput(BaseModel):
    chrom: str
    pos: int
    ref: str
    alt: str
    gene_symbol: str | None = None
    consequence: str | None = None
    gnomad_af: float | None = None
    clinvar_significance: str | None = None


class PredictionResponse(BaseModel):
    pathogenicity_probability: float
    predicted_class: str
    confidence: str
    model_used: str


class BatchPredictionRequest(BaseModel):
    variants: list[VariantInput]


class BatchPredictionResponse(BaseModel):
    predictions: list[PredictionResponse | dict[str, str]]


class ExplanationRequest(BaseModel):
    variant: VariantInput
    top_k: int = 10


class ExplanationResponse(BaseModel):
    variant_id: str
    prediction: float
    base_value: float
    summary: str
    top_positive_features: list[dict[str, Any]]
    top_negative_features: list[dict[str, Any]]


class TrainingRequest(BaseModel):
    model_types: list[str] = ["random_forest", "gradient_boosting", "xgboost"]
    cv_folds: int = 5
    test_size: float = 0.2
    optimize_hyperparams: bool = False


class TrainingResponse(BaseModel):
    status: str
    best_model: str | None = None
    best_cv_roc_auc: float | None = None
    results_summary: list[dict[str, Any]] | None = None
    message: str | None = None


class ModelInfo(BaseModel):
    filename: str
    model_name: str
    model_type: str
    cv_roc_auc: float
    test_roc_auc: float
    n_samples: int
    n_features: int
    size_mb: float


# Global integration instance
_integration: MutationMLIntegration | None = None


def get_integration() -> MutationMLIntegration:
    global _integration
    if _integration is None:
        _integration = MutationMLIntegration()
        _integration.load_model()
    return _integration


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    integration = get_integration()
    return {
        "status": "healthy",
        "model_loaded": integration.is_loaded(),
        "model_name": integration.training_result.model_name if integration.is_loaded() else None,
    }


@app.get("/models", response_model=list[ModelInfo])
async def list_models():
    """List all saved models."""
    model_files = list(MODEL_DIR.glob("*.pkl"))
    models = []
    
    for f in model_files:
        try:
            with open(f, "rb") as mf:
                data = pickle.load(mf)
            models.append(ModelInfo(
                filename=f.name,
                model_name=data.get("model_name", "Unknown"),
                model_type=data.get("model_type", "Unknown"),
                cv_roc_auc=data.get("cv_scores", {}).get("roc_auc", 0),
                test_roc_auc=data.get("test_scores", {}).get("roc_auc", 0),
                n_samples=data.get("n_samples", 0),
                n_features=data.get("n_features", 0),
                size_mb=round(f.stat().st_size / (1024 * 1024), 2),
            ))
        except Exception:
            continue
    
    return models


@app.post("/models/load/{filename}")
async def load_model(filename: str):
    """Load a specific model."""
    global _integration
    filepath = MODEL_DIR / filename
    
    if not filepath.exists():
        raise HTTPException(404, f"Model {filename} not found")
    
    _integration = MutationMLIntegration(model_path=filepath)
    if not _integration.load_model():
        raise HTTPException(500, "Failed to load model")
    
    return {
        "status": "loaded",
        "model": _integration.training_result.model_name,
        "type": _integration.training_result.model_type,
    }


@app.post("/predict", response_model=PredictionResponse)
async def predict_single(variant: VariantInput):
    """Predict pathogenicity for a single variant."""
    integration = get_integration()
    
    if not integration.is_loaded():
        raise HTTPException(503, "No model loaded. Load a model first.")
    
    try:
        result = integration.predict_single(
            variant.chrom,
            variant.pos,
            variant.ref,
            variant.alt,
            gene_symbol=variant.gene_symbol,
            consequence=variant.consequence,
            gnomad_af=variant.gnomad_af,
            clinvar_significance=variant.clinvar_significance,
        )
        return PredictionResponse(**result)
    except Exception as e:
        logger.error("Prediction failed: %s", e)
        raise HTTPException(500, f"Prediction failed: {e}")


@app.post("/predict/batch", response_model=BatchPredictionResponse)
async def predict_batch(request: BatchPredictionRequest):
    """Predict pathogenicity for multiple variants."""
    integration = get_integration()
    
    if not integration.is_loaded():
        raise HTTPException(503, "No model loaded. Load a model first.")
    
    variants = [v.model_dump() for v in request.variants]
    results = integration.batch_predict(variants)
    
    return BatchPredictionResponse(predictions=results)


@app.post("/predict/vcf")
async def predict_vcf(
    file: UploadFile = File(...),
    expected_build: str | None = Form(None),
    preview_limit: int = Form(1000),
):
    """Predict from VCF file."""
    integration = get_integration()
    
    if not integration.is_loaded():
        raise HTTPException(503, "No model loaded. Load a model first.")
    
    try:
        content = await file.read()
        
        # Use BytesIO for the stream
        import io
        vcf_stream = io.BytesIO(content)
        
        summary, enhanced = enhance_vcf_with_ml(
            vcf_stream,
            file.filename or "upload.vcf",
            integration,
            expected_build=expected_build,
            preview_limit=preview_limit,
        )
        
        predictions = [
            {
                "chrom": v.chrom,
                "pos": v.pos,
                "ref": v.ref,
                "alt": v.alt,
                "gene_symbol": v.gene_symbol,
                "consequence": v.consequence,
                "pathogenicity_probability": v.pathogenicity_probability,
                "predicted_class": v.predicted_class,
                "confidence": v.confidence,
                "shap_summary": v.shap_summary,
            }
            for v in enhanced if v.pathogenicity_probability is not None
        ]
        
        return {
            "summary": summary,
            "predictions": predictions,
            "count": len(predictions),
        }
    except Exception as e:
        logger.error("VCF prediction failed: %s", e)
        raise HTTPException(500, f"VCF prediction failed: {e}")


@app.post("/explain", response_model=ExplanationResponse)
async def explain_variant(request: ExplanationRequest):
    """Explain a variant prediction using SHAP."""
    integration = get_integration()
    
    if not integration.is_loaded():
        raise HTTPException(503, "No model loaded. Load a model first.")
    
    if integration.explainer is None:
        raise HTTPException(503, "SHAP explainer not available")
    
    try:
        variant_dict = request.variant.model_dump()
        explanation = integration.explainer.explain(variant_dict, top_k=request.top_k)
        
        return ExplanationResponse(
            variant_id=explanation.variant_id,
            prediction=explanation.prediction,
            base_value=explanation.base_value,
            summary=explanation.summary,
            top_positive_features=explanation.top_positive,
            top_negative_features=explanation.top_negative,
        )
    except Exception as e:
        logger.error("Explanation failed: %s", e)
        raise HTTPException(500, f"Explanation failed: {e}")


@app.post("/train", response_model=TrainingResponse)
async def train_model(
    request: TrainingRequest,
    pathogenic_vcf: list[UploadFile] = File([]),
    benign_vcf: list[UploadFile] = File([]),
):
    """Train mutation classifier from labeled VCF files."""
    if not pathogenic_vcf or not benign_vcf:
        raise HTTPException(400, "Both pathogenic and benign VCF files required")
    
    try:
        # Process VCFs
        patho_variants = []
        benign_variants = []
        
        for f in pathogenic_vcf:
            content = await f.read()
            import io
            summary, meta, preview = summarize_vcf_interpretation_stream(
                io.BytesIO(content), f.filename, preview_limit=10000
            )
            for v in preview:
                v["_label"] = 1
                patho_variants.append(v)
        
        for f in benign_vcf:
            content = await f.read()
            import io
            summary, meta, preview = summarize_vcf_interpretation_stream(
                io.BytesIO(content), f.filename, preview_limit=10000
            )
            for v in preview:
                v["_label"] = 0
                benign_variants.append(v)
        
        all_variants = patho_variants + benign_variants
        labels = [v.pop("_label") for v in all_variants]
        
        # Convert to feature matrix (simplified - would need full feature engineering)
        import pandas as pd
        df = pd.DataFrame(all_variants)
        
        # This is a placeholder - real implementation would use FeatureEngineer
        st.warning("Training from VCF requires full feature engineering pipeline. Use /train/matrix endpoint with pre-computed features.")
        
        return TrainingResponse(
            status="not_implemented",
            message="VCF-based training requires feature engineering. Use feature matrix endpoint.",
        )
        
    except Exception as e:
        logger.error("Training failed: %s", e)
        raise HTTPException(500, f"Training failed: {e}")


@app.post("/train/matrix", response_model=TrainingResponse)
async def train_from_matrix(
    request: TrainingRequest,
    file: UploadFile = File(...),
    target_column: str = Form(...),
):
    """Train from pre-computed feature matrix (CSV/Parquet)."""
    try:
        import io
        import pandas as pd
        
        content = await file.read()
        buffer = io.BytesIO(content)
        
        if file.filename.endswith(".parquet"):
            df = pd.read_parquet(buffer)
        else:
            df = pd.read_csv(buffer)
        
        if target_column not in df.columns:
            raise HTTPException(400, f"Target column '{target_column}' not found")
        
        X = df.drop(columns=[target_column]).values
        y = df[target_column].values
        feature_names = [c for c in df.columns if c != target_column]
        
        trainer = MutationMLTrainer(
            cv_folds=request.cv_folds,
            test_size=request.test_size,
            optimize_hyperparams=request.optimize_hyperparams,
        )
        
        results = trainer.train(X, y, feature_names)
        
        # Save best model
        best = trainer.get_best_model()
        if best:
            model_path = MODEL_DIR / f"mutation_model_{best.model_name}.pkl"
            trainer.save_model(best, model_path)
        
        return TrainingResponse(
            status="completed",
            best_model=best.model_name if best else None,
            best_cv_roc_auc=best.cv_scores["roc_auc"] if best else None,
            results_summary=trainer.get_results_summary().to_dict("records"),
        )
        
    except Exception as e:
        logger.error("Matrix training failed: %s", e)
        raise HTTPException(500, f"Training failed: {e}")


@app.delete("/models/{filename}")
async def delete_model(filename: str):
    """Delete a saved model."""
    filepath = MODEL_DIR / filename
    
    if not filepath.exists():
        raise HTTPException(404, f"Model {filename} not found")
    
    filepath.unlink()
    return {"status": "deleted", "filename": filename}


@app.get("/models/{filename}/download")
async def download_model(filename: str):
    """Download a model file."""
    from fastapi.responses import FileResponse
    
    filepath = MODEL_DIR / filename
    
    if not filepath.exists():
        raise HTTPException(404, f"Model {filename} not found")
    
    return FileResponse(
        filepath,
        media_type="application/octet-stream",
        filename=filename,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)