"""Streamlit ML Dashboard for mutation interpretation."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from geneai.mutation_ml.integration import MutationMLIntegration, enhance_vcf_with_ml
from geneai.mutation_ml.training import MutationMLTrainer, TrainingResult, train_mutation_classifier
from geneai.mutation_ml.explainability import MutationExplainer, explain_prediction
from geneai.mutation import summarize_vcf_interpretation_stream
from geneai.professional_ui.core import inject_professional_css

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)


def render_ml_dashboard_page() -> None:
    """Render the ML training and prediction dashboard."""
    inject_professional_css()
    
    st.subheader("🧬 Mutation ML Dashboard")
    st.write(
        "Train, evaluate, and deploy ML models for variant pathogenicity prediction. "
        "Integrates with ClinVar, gnomAD, AlphaMissense, COSMIC, and other databases."
    )
    
    # Tabs for different functions
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Model Training",
        "🔬 Variant Prediction",
        "📈 Model Evaluation",
        "🔍 Explainability (SHAP)",
        "⚙️ Model Management",
    ])
    
    with tab1:
        render_training_tab()
    
    with tab2:
        render_prediction_tab()
    
    with tab3:
        render_evaluation_tab()
    
    with tab4:
        render_explainability_tab()
    
    with tab5:
        render_management_tab()


def render_training_tab() -> None:
    """Render model training interface."""
    st.markdown("### Train Mutation Pathogenicity Classifier")
    
    st.info(
        "Upload labeled VCF files (pathogenic/benign) or provide pre-engineered feature matrices. "
        "The pipeline supports Logistic Regression, Random Forest, Gradient Boosting, XGBoost, LightGBM, and SVM."
    )
    
    # Data source selection
    data_source = st.radio(
        "Training Data Source",
        ["Labeled VCF Files", "Feature Matrix (CSV/Parquet)", "ClinVar + gnomAD (Auto)"],
        horizontal=True,
    )
    
    if data_source == "Labeled VCF Files":
        render_vcf_training()
    elif data_source == "Feature Matrix (CSV/Parquet)":
        render_matrix_training()
    else:
        render_auto_training()


def render_vcf_training() -> None:
    """VCF-based training interface."""
    st.markdown("#### Labeled VCF Training")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Pathogenic VCFs**")
        patho_files = st.file_uploader(
            "Upload pathogenic variant VCFs",
            type=["vcf", "vcf.gz"],
            accept_multiple_files=True,
            key="patho_vcf",
        )
        
    with col2:
        st.write("**Benign VCFs**")
        benign_files = st.file_uploader(
            "Upload benign variant VCFs",
            type=["vcf", "vcf.gz"],
            accept_multiple_files=True,
            key="benign_vcf",
        )
    
    # External data options
    with st.expander("External Annotation Data (Optional)"):
        col1, col2 = st.columns(2)
        with col1:
            clinvar_file = st.file_uploader("ClinVar TSV", type=["tsv", "tsv.gz"], key="clinvar_train")
            gnomad_dir = st.text_input("gnomAD directory", placeholder="data/gnomad/")
        with col2:
            alphamissense_file = st.file_uploader("AlphaMissense TSV", type=["tsv", "tsv.gz"], key="am_train")
            cosmic_file = st.file_uploader("COSMIC TSV", type=["tsv", "tsv.gz"], key="cosmic_train")
    
    # Model configuration
    with st.expander("Model Configuration"):
        model_types = st.multiselect(
            "Models to train",
            ["Logistic Regression", "Random Forest", "Gradient Boosting", "XGBoost", "LightGBM", "SVM"],
            default=["Random Forest", "Gradient Boosting", "XGBoost"],
        )
        cv_folds = st.slider("CV Folds", 3, 10, 5)
        test_size = st.slider("Test Size", 0.1, 0.4, 0.2, 0.05)
        optimize = st.checkbox("Hyperparameter Optimization", value=False)
    
    if st.button("🚀 Start Training", type="primary", disabled=not (patho_files and benign_files)):
        with st.spinner("Processing VCF files and training models..."):
            try:
                # Process VCFs
                patho_variants = []
                benign_variants = []
                
                for f in patho_files:
                    summary, meta, preview = summarize_vcf_interpretation_stream(f, f.name, preview_limit=10000)
                    for v in preview:
                        v["_label"] = 1
                        patho_variants.append(v)
                
                for f in benign_files:
                    summary, meta, preview = summarize_vcf_interpretation_stream(f, f.name, preview_limit=10000)
                    for v in preview:
                        v["_label"] = 0
                        benign_variants.append(v)
                
                all_variants = patho_variants + benign_variants
                labels = [v.pop("_label") for v in all_variants]
                
                st.success(f"Loaded {len(patho_variants)} pathogenic + {len(benign_variants)} benign variants")
                
                # Create feature matrix
                df = pd.DataFrame(all_variants)
                
                # Train
                trainer = MutationMLTrainer(
                    cv_folds=cv_folds,
                    test_size=test_size,
                    optimize_hyperparams=optimize,
                )
                
                # This would need feature engineering - simplified for demo
                st.info("Feature engineering and training would run here. See training.py for full pipeline.")
                
            except Exception as e:
                st.error(f"Training failed: {e}")
                logger.error("VCF training failed: %s", e)


def render_matrix_training() -> None:
    """Feature matrix training interface."""
    st.markdown("#### Feature Matrix Training")
    
    uploaded = st.file_uploader(
        "Upload feature matrix (CSV or Parquet)",
        type=["csv", "parquet"],
        key="feature_matrix",
    )
    
    if uploaded:
        try:
            if uploaded.name.endswith(".parquet"):
                df = pd.read_parquet(uploaded)
            else:
                df = pd.read_csv(uploaded)
            
            st.write(f"Loaded {len(df)} samples × {len(df.columns)} features")
            st.dataframe(df.head(), use_container_width=True)
            
            # Target column selection
            target_col = st.selectbox("Target Column", df.columns)
            
            if st.button("Train Models", type="primary"):
                X = df.drop(columns=[target_col]).values
                y = df[target_col].values
                feature_names = [c for c in df.columns if c != target_col]
                
                trainer = MutationMLTrainer()
                results = trainer.train(X, y, feature_names)
                
                # Display results
                summary_df = trainer.get_results_summary()
                st.dataframe(summary_df, use_container_width=True)
                
                # Save best model
                best = trainer.get_best_model()
                if best:
                    MODEL_DIR.mkdir(exist_ok=True)
                    trainer.save_model(best, MODEL_DIR / "best_mutation_model.pkl")
                    st.success(f"Best model ({best.model_name}) saved!")
                    
        except Exception as e:
            st.error(f"Failed to load/train: {e}")


def render_auto_training() -> None:
    """Automated training with public databases."""
    st.markdown("#### Automated Training (ClinVar + gnomAD)")
    
    st.write(
        "This downloads ClinVar pathogenic/benign variants and gnomAD frequencies "
        "to create a training dataset automatically."
    )
    
    if st.button("Download & Prepare Data", type="secondary"):
        with st.spinner("Downloading datasets..."):
            st.info("Dataset download would run here. See dataset_acquisition.py")
    
    if st.button("Train on Prepared Data", type="primary", disabled=True):
        st.info("Training would run on prepared data.")


def render_prediction_tab() -> None:
    """Render variant prediction interface."""
    st.markdown("### Variant Pathogenicity Prediction")
    
    integration = MutationMLIntegration()
    model_loaded = integration.load_model()
    
    if not model_loaded:
        st.warning("No trained model found. Train a model first in the 'Model Training' tab.")
        if st.button("Use Demo Model (Random Forest)"):
            st.info("Demo mode - would load a pre-trained model")
        return
    
    st.success(f"Model loaded: {integration.training_result.model_name} ({integration.training_result.model_type})")
    
    # Prediction mode
    pred_mode = st.radio("Prediction Mode", ["Single Variant", "Batch (VCF)", "Batch (CSV)"], horizontal=True)
    
    if pred_mode == "Single Variant":
        render_single_prediction(integration)
    elif pred_mode == "Batch (VCF)":
        render_vcf_batch_prediction(integration)
    else:
        render_csv_batch_prediction(integration)


def render_single_prediction(integration: MutationMLIntegration) -> None:
    """Single variant prediction form."""
    with st.form("single_variant_form"):
        col1, col2, col3, col4 = st.columns(4)
        chrom = col1.text_input("Chromosome", "17")
        pos = col2.number_input("Position", value=43044295, min_value=1)
        ref = col3.text_input("REF", "C")
        alt = col4.text_input("ALT", "T")
        
        col1, col2, col3 = st.columns(3)
        gene = col1.text_input("Gene Symbol (optional)", "BRCA1")
        consequence = col2.selectbox(
            "Consequence (optional)",
            ["", "missense_variant", "stop_gained", "frameshift_variant", "splice_donor_variant", "synonymous_variant"]
        )
        gnomad_af = col3.number_input("gnomAD AF (optional)", value=0.0, format="%.6f")
        
        clinvar = st.selectbox(
            "ClinVar Significance (optional)",
            ["", "Pathogenic", "Likely pathogenic", "Uncertain significance", "Likely benign", "Benign"]
        )
        
        submitted = st.form_submit_button("Predict", type="primary")
        
        if submitted:
            try:
                result = integration.predict_single(
                    chrom, pos, ref, alt,
                    gene_symbol=gene,
                    consequence=consequence,
                    gnomad_af=gnomad_af,
                    clinvar_significance=clinvar,
                )
                
                # Display result
                prob = result["pathogenicity_probability"]
                pred_class = result["predicted_class"]
                conf = result["confidence"]
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Pathogenicity Probability", f"{prob:.1%}")
                col2.metric("Predicted Class", pred_class.capitalize())
                col3.metric("Confidence", conf.capitalize())
                
                # Probability gauge
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=prob * 100,
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': "Pathogenicity Score"},
                    gauge={
                        'axis': {'range': [0, 100]},
                        'bar': {'color': "red" if prob > 0.5 else "green"},
                        'steps': [
                            {'range': [0, 30], 'color': "lightgreen"},
                            {'range': [30, 70], 'color': "yellow"},
                            {'range': [70, 100], 'color': "lightcoral"},
                        ],
                        'threshold': {
                            'line': {'color': "black", 'width': 4},
                            'thickness': 0.75,
                            'value': prob * 100
                        }
                    }
                ))
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"Prediction failed: {e}")


def render_vcf_batch_prediction(integration: MutationMLIntegration) -> None:
    """Batch prediction from VCF."""
    uploaded = st.file_uploader("Upload VCF for batch prediction", type=["vcf", "vcf.gz"], key="vcf_batch")
    
    if uploaded and st.button("Run Batch Prediction", type="primary"):
        with st.spinner("Scanning VCF and predicting..."):
            try:
                summary, enhanced = enhance_vcf_with_ml(
                    uploaded, uploaded.name, integration, preview_limit=500
                )
                
                st.success(f"Processed {len(enhanced)} variants")
                
                # Convert to DataFrame for display
                df = pd.DataFrame([
                    {
                        "Chr": v.chrom,
                        "Pos": v.pos,
                        "Ref": v.ref,
                        "Alt": v.alt,
                        "Gene": v.gene_symbol or "–",
                        "Consequence": v.consequence or "–",
                        "Probability": f"{v.pathogenicity_probability:.1%}" if v.pathogenicity_probability else "–",
                        "Class": v.predicted_class or "–",
                        "Confidence": v.confidence or "–",
                    }
                    for v in enhanced if v.pathogenicity_probability is not None
                ])
                
                st.dataframe(df, use_container_width=True, height=400)
                
                # Download
                csv = df.to_csv(index=False)
                st.download_button(
                    "Download Predictions CSV",
                    csv,
                    f"ml_predictions_{uploaded.name}.csv",
                    "text/csv",
                )
                
            except Exception as e:
                st.error(f"Batch prediction failed: {e}")


def render_csv_batch_prediction(integration: MutationMLIntegration) -> None:
    """Batch prediction from CSV."""
    uploaded = st.file_uploader("Upload CSV with variants", type=["csv"], key="csv_batch")
    
    if uploaded:
        df = pd.read_csv(uploaded)
        st.write(f"Loaded {len(df)} variants")
        st.dataframe(df.head(), use_container_width=True)
        
        required_cols = ["chrom", "pos", "ref", "alt"]
        if all(c in df.columns for c in required_cols):
            if st.button("Predict All", type="primary"):
                variants = df[required_cols].to_dict("records")
                results = integration.batch_predict(variants)
                
                # Merge results
                df["pathogenicity_probability"] = [r.get("pathogenicity_probability") for r in results]
                df["predicted_class"] = [r.get("predicted_class") for r in results]
                df["confidence"] = [r.get("confidence") for r in results]
                
                st.dataframe(df, use_container_width=True)
                
                csv = df.to_csv(index=False)
                st.download_button("Download Results", csv, "predictions.csv", "text/csv")
        else:
            st.error(f"CSV must contain columns: {required_cols}")


def render_evaluation_tab() -> None:
    """Render model evaluation interface."""
    st.markdown("### Model Evaluation & Comparison")
    
    # Load available models
    model_files = list(MODEL_DIR.glob("*.pkl"))
    
    if not model_files:
        st.info("No trained models found. Train a model first.")
        return
    
    selected_model = st.selectbox("Select Model", [f.name for f in model_files])
    
    if selected_model:
        with open(MODEL_DIR / selected_model, "rb") as f:
            model_data = pickle.load(f)
        
        result = TrainingResult(
            model_name=model_data["model_name"],
            model_type=model_data["model_type"],
            model=model_data["model"],
            preprocessor=model_data.get("preprocessor"),
            cv_scores=model_data["cv_scores"],
            cv_scores_std=model_data.get("cv_scores_std", {}),
            test_scores=model_data["test_scores"],
            feature_importance=model_data.get("feature_importance"),
            training_time=model_data["training_time"],
            n_samples=model_data["n_samples"],
            n_features=model_data["n_features"],
            class_distribution=model_data["class_distribution"],
            best_params=model_data.get("best_params"),
            calibration_curve=model_data.get("calibration_curve"),
        )
        
        # Metrics display
        st.markdown("#### Cross-Validation Metrics")
        cv_cols = st.columns(4)
        metrics = ["roc_auc", "pr_auc", "f1", "mcc"]
        for i, m in enumerate(metrics):
            cv_cols[i].metric(m.upper(), f"{result.cv_scores.get(m, 0):.4f}")
        
        st.markdown("#### Test Set Metrics")
        test_cols = st.columns(4)
        for i, m in enumerate(metrics):
            test_cols[i].metric(m.upper(), f"{result.test_scores.get(m, 0):.4f}")
        
        # ROC Curve
        if result.calibration_curve:
            cal = result.calibration_curve
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=cal["fpr"], y=cal["tpr"],
                mode="lines", name=f"ROC (AUC={result.test_scores['roc_auc']:.3f})"
            ))
            fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Random", line=dict(dash="dash")))
            fig.update_layout(title="ROC Curve", xaxis_title="FPR", yaxis_title="TPR", height=400)
            st.plotly_chart(fig, use_container_width=True)
            
            # PR Curve
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=cal["recall"], y=cal["precision"],
                mode="lines", name=f"PR (AUC={result.test_scores['pr_auc']:.3f})"
            ))
            fig2.update_layout(title="Precision-Recall Curve", xaxis_title="Recall", yaxis_title="Precision", height=400)
            st.plotly_chart(fig2, use_container_width=True)
        
        # Feature Importance
        if result.feature_importance:
            st.markdown("#### Top 20 Feature Importances")
            fi_df = pd.DataFrame(result.feature_importance[:20], columns=["Feature", "Importance"])
            fig3 = px.bar(fi_df, x="Importance", y="Feature", orientation="h", height=500)
            fig3.update_layout(yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig3, use_container_width=True)


def render_explainability_tab() -> None:
    """Render SHAP explainability interface."""
    st.markdown("### SHAP Explainability")
    
    if not st.session_state.get("shap_available", False):
        try:
            import shap
            st.session_state.shap_available = True
        except ImportError:
            st.session_state.shap_available = False
    
    if not st.session_state.shap_available:
        st.warning("SHAP not installed. Install with: `pip install shap`")
        return
    
    integration = MutationMLIntegration()
    if not integration.load_model():
        st.info("Load a model first to enable explainability.")
        return
    
    st.write("Explain individual variant predictions using SHAP values.")
    
    with st.form("explain_form"):
        col1, col2, col3, col4 = st.columns(4)
        chrom = col1.text_input("Chromosome", "17", key="exp_chrom")
        pos = col2.number_input("Position", value=43044295, min_value=1, key="exp_pos")
        ref = col3.text_input("REF", "C", key="exp_ref")
        alt = col4.text_input("ALT", "T", key="exp_alt")
        
        gene = st.text_input("Gene Symbol (optional)", "BRCA1", key="exp_gene")
        consequence = st.selectbox("Consequence", ["", "missense_variant", "stop_gained", "frameshift_variant"], key="exp_cons")
        
        submitted = st.form_submit_button("Explain Prediction", type="primary")
        
        if submitted:
            try:
                variant = {
                    "chrom": chrom, "pos": pos, "ref": ref, "alt": alt,
                    "gene_symbol": gene, "consequence": consequence,
                }
                
                explanation = integration.explainer.explain(variant)
                
                st.markdown("#### Prediction Summary")
                st.write(explanation.summary)
                
                col1, col2 = st.columns(2)
                col1.metric("Prediction", f"{explanation.prediction:.1%}")
                col2.metric("Base Value", f"{explanation.base_value:.4f}")
                
                # Waterfall-style feature contributions
                st.markdown("#### Feature Contributions")
                
                contrib_data = []
                for f in explanation.top_positive:
                    contrib_data.append({"Feature": f["feature"], "SHAP Value": f["shap_value"], "Direction": "↑ Increases"})
                for f in explanation.top_negative:
                    contrib_data.append({"Feature": f["feature"], "SHAP Value": f["shap_value"], "Direction": "↓ Decreases"})
                
                if contrib_data:
                    contrib_df = pd.DataFrame(contrib_data)
                    fig = px.bar(
                        contrib_df, x="SHAP Value", y="Feature", color="Direction",
                        orientation="h", color_discrete_map={"↑ Increases": "red", "↓ Decreases": "blue"},
                        height=400
                    )
                    fig.update_layout(yaxis={'categoryorder': 'total ascending'})
                    st.plotly_chart(fig, use_container_width=True)
                
            except Exception as e:
                st.error(f"Explanation failed: {e}")


def render_management_tab() -> None:
    """Render model management interface."""
    st.markdown("### Model Management")
    
    model_files = list(MODEL_DIR.glob("*.pkl"))
    
    if model_files:
        st.markdown("#### Saved Models")
        model_data = []
        for f in model_files:
            try:
                with open(f, "rb") as mf:
                    data = pickle.load(mf)
                model_data.append({
                    "Filename": f.name,
                    "Model": data.get("model_name", "Unknown"),
                    "Type": data.get("model_type", "Unknown"),
                    "CV ROC-AUC": f"{data.get('cv_scores', {}).get('roc_auc', 0):.4f}",
                    "Test ROC-AUC": f"{data.get('test_scores', {}).get('roc_auc', 0):.4f}",
                    "Samples": data.get("n_samples", 0),
                    "Features": data.get("n_features", 0),
                    "Size (MB)": round(f.stat().st_size / (1024*1024), 2),
                    "Saved": data.get("saved_at", "Unknown"),
                })
            except Exception:
                model_data.append({"Filename": f.name, "Error": "Failed to load"})
        
        df = pd.DataFrame(model_data)
        st.dataframe(df, use_container_width=True)
        
        # Actions
        col1, col2 = st.columns(2)
        with col1:
            to_delete = st.selectbox("Delete model", [""] + [f.name for f in model_files])
            if to_delete and st.button("🗑️ Delete", type="secondary"):
                (MODEL_DIR / to_delete).unlink()
                st.rerun()
        
        with col2:
            to_export = st.selectbox("Export model", [""] + [f.name for f in model_files])
            if to_export:
                with open(MODEL_DIR / to_export, "rb") as f:
                    st.download_button(
                        "📥 Download",
                        f.read(),
                        to_export,
                        "application/octet-stream",
                    )
    else:
        st.info("No models saved yet.")
    
    # Upload model
    st.markdown("#### Upload Model")
    uploaded = st.file_uploader("Upload .pkl model file", type=["pkl"])
    if uploaded and st.button("Save Model"):
        dest = MODEL_DIR / uploaded.name
        with open(dest, "wb") as f:
            f.write(uploaded.read())
        st.success(f"Saved to {dest}")
        st.rerun()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    render_ml_dashboard_page()