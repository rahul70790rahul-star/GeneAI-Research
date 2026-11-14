"""Drug discovery intelligence - connecting paper findings with GeneAI modules."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from geneai.drug_discovery import drug_database as db
from geneai.drug_discovery import chembl_client
from geneai.drug_discovery import pubchem_client
from geneai.drug_target_prediction import prediction_engine as dt_prediction
from geneai.drug_repurposing import repurposing_engine as dr_engine
from geneai.research_analysis.paper_analyzer import DrugTargetRelationship

logger = logging.getLogger(__name__)


@dataclass
class DrugTargetIntelligence:
    """Drug-target intelligence from paper analysis."""
    drug_name: str
    target_name: str
    relationship_type: str
    evidence_type: str  # experimental, computational, clinical, review
    source_papers: list[dict[str, Any]] = field(default_factory=list)
    chembl_data: dict[str, Any] | None = None
    pubchem_data: dict[str, Any] | None = None
    prediction_score: float | None = None
    repurposing_score: float | None = None
    known_interactions: list[dict[str, Any]] = field(default_factory=list)
    validation_status: str = "literature_only"  # literature_only, computationally_predicted, experimentally_validated, clinical
    confidence: str = "medium"


@dataclass
class DiseaseTargetIntelligence:
    """Disease-target intelligence from paper analysis."""
    disease_name: str
    target_name: str
    association_type: str  # genetic, expression, pathway, literature
    evidence_strength: str  # strong, moderate, weak
    source_papers: list[dict[str, Any]] = field(default_factory=list)
    opentargets_score: float | None = None
    known_drugs: list[dict[str, Any]] = field(default_factory=list)
    druggability_assessment: dict[str, Any] | None = None
    repurposing_opportunities: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TherapeuticCompoundIntelligence:
    """Therapeutic compound intelligence from paper analysis."""
    compound_name: str
    target_diseases: list[str] = field(default_factory=list)
    target_proteins: list[str] = field(default_factory=list)
    mechanism_of_action: str = ""
    experimental_evidence: list[dict[str, Any]] = field(default_factory=list)
    clinical_trials: list[dict[str, Any]] = field(default_factory=list)
    chembl_data: dict[str, Any] | None = None
    pubchem_data: dict[str, Any] | None = None
    prediction_affinity: dict[str, float] | None = None
    repurposing_potential: str = "unknown"


def enrich_drug_target_relationships(
    relationships: list[DrugTargetRelationship],
) -> list[DrugTargetIntelligence]:
    """Enrich drug-target relationships with GeneAI module data."""
    enriched = []

    for rel in relationships:
        intelligence = DrugTargetIntelligence(
            drug_name=rel.drug_name,
            target_name=rel.target_name,
            relationship_type=rel.relationship_type,
            evidence_type=rel.evidence_type,
            source_papers=[{
                "pmid": rel.pmid,
                "doi": rel.doi,
                "context": rel.source_text,
                "confidence": rel.confidence,
            }],
        )

        # Try to get ChEMBL data for drug
        try:
            # Search ChEMBL for drug
            drug_results = chembl_client.search_molecules_by_name(rel.drug_name, limit=1)
            if drug_results:
                drug = drug_results[0]
                intelligence.chembl_data = {
                    "chembl_id": drug.get("chembl_id"),
                    "pref_name": drug.get("pref_name"),
                    "max_phase": drug.get("max_phase"),
                    "first_approval": drug.get("first_approval"),
                    "mechanism": drug.get("mechanism_of_action"),
                    "target_chembl_id": drug.get("target_chembl_id"),
                }
        except Exception as e:
            logger.warning("ChEMBL lookup failed for %s: %s", rel.drug_name, e)

        # Try to get PubChem data for drug
        try:
            pubchem_results = pubchem_client.get_compound_by_name(rel.drug_name)
            if pubchem_results:
                pc = pubchem_results[0]
                intelligence.pubchem_data = {
                    "cid": pc.get("cid"),
                    "canonical_smiles": pc.get("canonical_smiles"),
                    "molecular_weight": pc.get("molecular_weight"),
                    "molecular_formula": pc.get("molecular_formula"),
                    "xlogp3": pc.get("xlogp3"),
                    "tpsa": pc.get("tpsa"),
                }
        except Exception as e:
            logger.warning("PubChem lookup failed for %s: %s", rel.drug_name, e)

        # Get prediction from Phase 4.7 drug-target prediction engine
        try:
            if intelligence.pubchem_data and intelligence.pubchem_data.get("canonical_smiles"):
                pred_engine = dt_prediction.DrugTargetPredictionEngine()
                pred = pred_engine.predict_drug_target(
                    drug_identifier=intelligence.pubchem_data["canonical_smiles"],
                    target_identifier=rel.target_name,
                    identifier_type="smiles",
                )
                intelligence.prediction_score = pred.get("interaction_probability")
        except Exception as e:
            logger.warning("Drug-target prediction failed: %s", e)

        # Check local database for known interactions
        try:
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT d.name, t.gene_symbol, dti.action_type, dti.binding_affinity_nm, dti.source
                FROM drug_target_interactions dti
                JOIN drugs d ON dti.drug_id = d.id
                JOIN targets t ON dti.target_id = t.id
                WHERE d.name LIKE ? OR t.gene_symbol LIKE ?
            """, (f"%{rel.drug_name}%", f"%{rel.target_name}%"))
            rows = cursor.fetchall()
            conn.close()

            for row in rows:
                intelligence.known_interactions.append({
                    "drug": row[0],
                    "target": row[1],
                    "action_type": row[2],
                    "affinity_nm": row[3],
                    "source": row[4],
                })

            if intelligence.known_interactions:
                intelligence.validation_status = "experimentally_validated"
        except Exception as e:
            logger.warning("Database lookup failed: %s", e)

        # Assess confidence
        if intelligence.known_interactions:
            intelligence.confidence = "high"
        elif intelligence.prediction_score and intelligence.prediction_score > 0.7:
            intelligence.confidence = "high"
        elif intelligence.chembl_data or intelligence.pubchem_data:
            intelligence.confidence = "medium"
        else:
            intelligence.confidence = "low"

        enriched.append(intelligence)

    return enriched


def identify_disease_target_associations(
    analyzed_papers: list[dict[str, Any]],
) -> list[DiseaseTargetIntelligence]:
    """Identify disease-target associations from papers and enrich with OpenTargets."""
    from geneai.drug_discovery import opentargets_client

    associations = []

    # Extract disease-target pairs from papers
    disease_target_pairs = set()
    for paper in analyzed_papers:
        entities = paper.get("entities", {})
        metadata = paper.get("metadata", {})

        diseases = [d.get("name", "").lower() for d in entities.get("diseases", []) if d.get("name")]
        genes = [g.get("symbol", "").upper() for g in entities.get("genes", []) if g.get("symbol")]

        for disease in diseases:
            for gene in genes:
                disease_target_pairs.add((disease, gene))

    for disease, gene in disease_target_pairs:
        intelligence = DiseaseTargetIntelligence(
            disease_name=disease,
            target_name=gene,
            association_type="literature",
            evidence_strength="weak",
            source_papers=[],
        )

        # Collect supporting papers
        for paper in analyzed_papers:
            entities = paper.get("entities", {})
            paper_diseases = [d.get("name", "").lower() for d in entities.get("diseases", [])]
            paper_genes = [g.get("symbol", "").upper() for g in entities.get("genes", [])]
            if disease in paper_diseases and gene in paper_genes:
                metadata = paper.get("metadata", {})
                intelligence.source_papers.append({
                    "pmid": metadata.get("pmid"),
                    "doi": metadata.get("doi"),
                    "title": metadata.get("title", "")[:100],
                })

        intelligence.evidence_strength = "strong" if len(intelligence.source_papers) >= 3 else (
            "moderate" if len(intelligence.source_papers) >= 2 else "weak"
        )

        # Enrich with OpenTargets
        try:
            # Search for disease
            ot_diseases = opentargets_client.search_diseases(disease, limit=5)
            for ot_disease in ot_diseases:
                if disease in ot_disease.get("name", "").lower():
                    disease_id = ot_disease.get("disease_id")
                    if disease_id:
                        ot_targets = opentargets_client.get_disease_targets(disease_id, limit=50)
                        for ot_target in ot_targets:
                            if ot_target.get("target_symbol", "").upper() == gene:
                                intelligence.opentargets_score = ot_target.get("score")
                                intelligence.association_type = "opentargets_validated"
                                break
        except Exception as e:
            logger.warning("OpenTargets lookup failed for %s-%s: %s", disease, gene, e)

        # Get known drugs for this target
        try:
            if intelligence.opentargets_score:
                ot_drugs = opentargets_client.get_target_drugs(gene, limit=10)
                intelligence.known_drugs = ot_drugs
        except Exception as e:
            logger.warning("OpenTargets drug lookup failed: %s", e)

        # Druggability assessment from Phase 4.5
        try:
            from geneai.drug_discovery import druggability_engine
            druggability = druggability_engine.assess_target_druggability(gene)
            intelligence.druggability_assessment = druggability
        except Exception as e:
            logger.warning("Druggability assessment failed: %s", e)

        # Repurposing opportunities from Phase 4.6
        try:
            repurposing = dr_engine.DrugRepurposingEngine()
            candidates = repurposing.find_repurposing_opportunities(disease, limit=5)
            intelligence.repurposing_opportunities = [
                {
                    "drug": c.drug_name,
                    "score": c.final_score,
                    "mechanism": c.mechanism_of_action,
                }
                for c in candidates
            ]
        except Exception as e:
            logger.warning("Repurposing search failed: %s", e)

        associations.append(intelligence)

    return associations


def identify_therapeutic_compounds(
    analyzed_papers: list[dict[str, Any]],
) -> list[TherapeuticCompoundIntelligence]:
    """Identify therapeutic compounds from papers."""
    compounds = {}

    for paper in analyzed_papers:
        entities = paper.get("entities", {})
        metadata = paper.get("metadata", {})
        dt_rels = paper.get("drug_target_relationships", [])

        for drug_entity in entities.get("drugs", []):
            name = drug_entity.get("name", "").lower()
            if not name:
                continue

            if name not in compounds:
                compounds[name] = TherapeuticCompoundIntelligence(compound_name=name)

            comp = compounds[name]
            comp.experimental_evidence.append({
                "pmid": metadata.get("pmid"),
                "doi": metadata.get("doi"),
                "title": metadata.get("title", "")[:100],
                "context": drug_entity.get("source_text", ""),
            })

            # Add diseases and targets from same paper
            for disease in entities.get("diseases", []):
                d_name = disease.get("name", "")
                if d_name and d_name not in comp.target_diseases:
                    comp.target_diseases.append(d_name)

            for gene in entities.get("genes", []):
                g_name = gene.get("symbol", "")
                if g_name and g_name not in comp.target_proteins:
                    comp.target_proteins.append(g_name)

            # Add drug-target relationships
            for rel in dt_rels:
                if rel.drug_name.lower() == name:
                    if rel.target_name not in comp.target_proteins:
                        comp.target_proteins.append(rel.target_name)
                    comp.mechanism_of_action = rel.relationship_type

    # Enrich with ChEMBL and PubChem
    for name, comp in compounds.items():
        try:
            drug_results = chembl_client.search_molecules_by_name(name, limit=1)
            if drug_results:
                drug = drug_results[0]
                comp.chembl_data = {
                    "chembl_id": drug.get("chembl_id"),
                    "pref_name": drug.get("pref_name"),
                    "max_phase": drug.get("max_phase"),
                    "mechanism": drug.get("mechanism_of_action"),
                }

                # Get clinical trials
                if drug.get("chembl_id"):
                    trials = chembl_client.get_molecule_trials(drug["chembl_id"], limit=5)
                    comp.clinical_trials = trials
        except Exception as e:
            logger.warning("ChEMBL enrichment failed for %s: %s", name, e)

        try:
            pubchem_results = pubchem_client.get_compound_by_name(name)
            if pubchem_results:
                pc = pubchem_results[0]
                comp.pubchem_data = {
                    "cid": pc.get("cid"),
                    "canonical_smiles": pc.get("canonical_smiles"),
                    "molecular_weight": pc.get("molecular_weight"),
                }
        except Exception as e:
            logger.warning("PubChem enrichment failed for %s: %s", name, e)

        # Predict binding affinity using Phase 4.7
        if comp.pubchem_data and comp.pubchem_data.get("canonical_smiles"):
            try:
                from geneai.drug_target_prediction import binding_affinity
                for target in comp.target_proteins[:5]:
                    affinity = binding_affinity.estimate_binding_affinity(
                        comp.pubchem_data["canonical_smiles"],
                        target,
                        method="ml",
                    )
                    if comp.prediction_affinity is None:
                        comp.prediction_affinity = {}
                    comp.prediction_affinity[target] = affinity.get("estimated_affinity_nm")
            except Exception as e:
                logger.warning("Affinity prediction failed for %s: %s", name, e)

        # Assess repurposing potential
        if comp.target_diseases and comp.target_proteins:
            comp.repurposing_potential = "high" if len(comp.target_diseases) > 1 else "moderate"

    return list(compounds.values())


def generate_drug_discovery_report(
    analyzed_papers: list[dict[str, Any]],
    output_path: str | None = None,
) -> dict[str, Any]:
    """Generate comprehensive drug discovery intelligence report."""
    # Enrich drug-target relationships
    all_relationships = []
    for paper in analyzed_papers:
        all_relationships.extend(paper.get("drug_target_relationships", []))

    enriched_relationships = enrich_drug_target_relationships(all_relationships)

    # Identify disease-target associations
    disease_targets = identify_disease_target_associations(analyzed_papers)

    # Identify therapeutic compounds
    compounds = identify_therapeutic_compounds(analyzed_papers)

    report = {
        "report_metadata": {
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "papers_analyzed": len(analyzed_papers),
            "total_relationships": len(enriched_relationships),
            "total_disease_targets": len(disease_targets),
            "total_compounds": len(compounds),
        },
        "drug_target_intelligence": [r.__dict__ for r in enriched_relationships],
        "disease_target_intelligence": [r.__dict__ for r in disease_targets],
        "therapeutic_compounds": [r.__dict__ for r in compounds],
        "summary": {
            "validated_interactions": sum(1 for r in enriched_relationships if r.validation_status == "experimentally_validated"),
            "predicted_interactions": sum(1 for r in enriched_relationships if r.prediction_score and r.prediction_score > 0.5),
            "high_confidence_disease_targets": sum(1 for r in disease_targets if r.evidence_strength == "strong"),
            "repurposing_candidates": sum(1 for c in compounds if c.repurposing_potential in ["high", "moderate"]),
        },
    }

    if output_path:
        import json
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

    return report