# GeneAI Research — Scientific Validation Report

**Audit date:** 2026-11-13  
**Project:** GeneAI Research, Phases 1–7  
**Scope:** Scientific correctness, evidence preservation, physical/biological plausibility, and independent validation of outputs  
**Companion documents:** `Complete_Audit_Report.md`, `Functional_Test_Report.md`, `ML_Model_Audit_Report.md`, `Missing_Features_Report.md`, `Priority_Improvement_Roadmap.md`

> **Validation rule:** an output is scientifically `PASS` only when it was compared with an authoritative external record or a documented physical/biological expectation. A feature that merely runs is not scientifically validated. Where no independent reference, model artefact, or benchmark was available, the item is `UNVERIFIED` — not “probably correct”.

---

## 1. Executive verdict

**The Phase 1–3 parsing and evidence-retrieval layer is scientifically credible for the narrow tasks it performs. The Phase 4–7 modelling, docking, ADMET, safety, repurposing, and genomic-intelligence layers are not scientifically validated and, in several places, are not scientifically meaningful as implemented.**

| Domain | Status | Basis |
|---|---|---|
| Sequence parsing and composition | **PASS** | Real NCBI records matched length and GC. |
| VCF allele parsing | **PASS** | Real and crafted variants classified correctly. |
| Variant normalization/REF validation | **UNVERIFIED** | Requires a reference FASTA; not exercised. |
| ClinVar retrieval | **PASS** | Correct accession, HGVS, classification, review status. |
| Mutation interpretation | **PASS** | Evidence-preserving; no unsupported pathogenicity claim. |
| Protein structure retrieval | **PARTIAL** | PDB entry and AlphaFold work; PDB search endpoint is wrong. |
| Docking | **FAIL** | Random rigid-body rotation; no docking engine installed. |
| Scoring functions | **FAIL** | Approximations labelled as Vina/RF-Score/NNScore; MM/GBSA GB term returns 0. |
| Drug-target prediction | **FAIL** | Cannot run; feature contract broken; demo data confounded. |
| ADMET | **FAIL** | No trained models; sample training data empty. |
| Drug safety | **FAIL** | Synthetic random toxicity data. |
| Drug repurposing | **PARTIAL** | Real/honest evidence pieces mixed with heuristic and placeholder scores. |
| Biomarker discovery | **PARTIAL** | Reasonable sklearn methodology, but no dataset and no validation. |
| Genome browser conservation | **FAIL** | Random beta-distributed values displayed as PhastCons. |
| AI research reports | **FAIL** | “Simulated” annotation and a fabricated DOI. |
| Integrated precision pipeline | **FAIL** | Literature/ML stages are placeholders. |

---

## 2. Evidence standard and limitations

### 2.1 What counts as validation

| Level | Definition | Used here |
|---|---|---|
| L1 — External record match | Output compared with an authoritative database record (NCBI, ClinVar, UniProt, PDB, ChEMBL). | Yes |
| L2 — Deterministic re-computation | Output re-derived independently from the same input (e.g. GC from sequence). | Yes |
| L3 — Benchmark/held-out test | Model or algorithm scored on an independent, documented benchmark. | **No** — no artefacts/benchmarks existed |
| L4 — Experimental/physical validation | Docking pose compared with crystal structure; ADMET compared with assay. | **No** |

Most Phase 4–7 claims sit at L3/L4, where **no validation was possible** because no trained models, benchmark sets, or experimental comparisons are bundled.

### 2.2 Limitations

- No licensed datasets (DrugBank, TTD, proprietary ADMET sets) were available.
- No trained model artefacts (`*.pkl`, `*.joblib`, `*.pt`, `*.h5`, `*.onnx`) exist in the repository.
- No docking binaries (`vina`, `smina`, `gnina`, `qvina2`, `qvina-w`) are on `PATH`.
- No cloud/LLM credentials were available.
- The audit did not run molecular dynamics, free-energy perturbation, or wet-lab assays.
- Python 3.15.2 was used; the project targets 3.11. This is an environment mismatch, not a scientific finding.

---

## 3. Sequence analysis

### SV-01 — Reference length and GC content

| Field | Value |
|---|---|
| Test | Parse NCBI `NM_007294.4` (BRCA1) and `NM_000546.6` (TP53); compare length with NCBI `slen`; recompute GC. |
| Expected | Parsed length equals `slen`; GC equals independently computed value. |
| Observed | BRCA1: 7,088 bp = `slen` 7,088; GC 41.77% (independent 41.775%). TP53: 2,512 bp = `slen` 2,512; GC 53.38% (independent 53.384%). |
| Status | **PASS** |
| Evidence | `%TEMP%\geneai_audit_realdata.json` |
| Scientific note | Length/GC are necessary but not sufficient for a sequence tool; they confirm the parser does not truncate, pad, or misread the record. |

### SV-02 — Ambiguous-base handling

| Field | Value |
|---|---|
| Observed | BRCA1 record reported 0 ambiguous bases; composition and GC were computed from the same sequence. |
| Status | **PASS** (for this record) |
| Scientific note | Records containing N/IUPAC ambiguity were not exhaustively tested; the parser exposes an ambiguous count rather than silently dropping bases. |

### SV-03 — ORF detection and translation

| Field | Value |
|---|---|
| Observed | The analysis object exposes `orfs`, `codons_frame_1`, `translation_frame_1`, and `sequence_type`. |
| Validation performed | None against RefSeq CDS/protein coordinates. |
| Status | **UNVERIFIED** |
| Why | Correct ORF calling requires strand, frame, start/stop codon, and transcript-coordinate conventions; the audit did not compare outputs with an authoritative CDS annotation. |
| Risk | A translation panel can look authoritative even if frame/strand handling is wrong. It must not be used for protein-level conclusions until validated. |

### SV-04 — FASTQ quality interpretation

| Field | Value |
|---|---|
| Status | **UNVERIFIED** |
| Why | No real FASTQ was exercised end-to-end. |

---

## 4. VCF analysis

### SV-05 — Allele-level parsing

| Field | Value |
|---|---|
| Input | vcflib `sample.vcf` (2,050 bytes). |
| Expected | 9 data rows; multiallelic ALT expanded; dot-ALT skipped. |
| Observed | 9 rows → 10 alleles; 6 SNP, 4 INDEL; 3 multiallelic rows; 2 dot-ALT rows skipped. |
| Status | **PASS** |
| Scientific note | This is a parsing result, not an annotation or clinical interpretation. The product states this explicitly. |

### SV-06 — Variant-class classification

| Field | Value |
|---|---|
| Cases | SNV `C→T`; insertion `C→CAG`; deletion `CAG→C`; MNV `CA→TG`; multiallelic `C→T,G`; symbolic `<DEL>`; `*` allele. |
| Observed | `SNP`, `INDEL`, `INDEL`, `COMPLEX`, two `SNP`s, `SYMBOLIC`, `SYMBOLIC`. |
| Status | **PASS** |
| Scientific note | `*` being labelled `SYMBOLIC` is defensible for a parser that does not resolve spanning-deletion semantics; it should not be interpreted as a deletion without a reference. |

### SV-07 — Genotype and QUAL statistics

| Field | Value |
|---|---|
| Observed | 3 samples; `HOM_REF=9, HET=12, HOM_ALT=3, OTHER_ALT=6`; mean QUAL 30.56 (min 3.0, max 67.0); 0 duplicate alleles. |
| Status | **PASS** (internal consistency with the source VCF) |
| Scientific note | QUAL is a per-record phred-scaled confidence, not a probability of pathogenicity. The UI does not conflate the two. |

### SV-08 — REF validation and indel normalization

| Field | Value |
|---|---|
| Status | **UNVERIFIED** |
| Why | The product requires a reference FASTA; none was configured. The product’s own summary states: “Not verified: reference FASTA is required for REF validation and indel normalization.” |
| Scientific consequence | Without REF checks, a VCF with incorrect reference alleles can be parsed as valid. Without left-normalization, equivalent indels can appear distinct. |
| Required validation | Compare normalized alleles with `bcftools norm` against GRCh38 for a documented variant set. |

### SV-09 — Annotation claims

| Field | Value |
|---|---|
| Observed | Embedded annotation counts were all zero for the real VCF; the UI displays source assertions only if present and states that parsing is not annotation. |
| Status | **PASS** (honesty) |
| Scientific note | No consequence prediction, gnomAD frequency, or ACMG classification is generated. This is the correct behaviour given the available evidence. |

---

## 5. Clinical variant retrieval and interpretation

### SV-10 — ClinVar record fidelity

| Field | Value |
|---|---|
| Query | `rs80357906` |
| Observed | `VCV000017677`; `NM_007294.4(BRCA1):c.5266dup (p.Gln1756fs)`; germline **Pathogenic**; review status **reviewed by expert panel**; last evaluated 2016-04-22; GRCh38 `17:43057062-43057063`; GRCh37 `17:41209079-41209080`. |
| Status | **PASS** |
| Scientific note | The retrieval preserves the source classification and review status. It does not independently re-classify the variant. |

### SV-11 — Clinical decision support

| Field | Value |
|---|---|
| Status | **NOT PRESENT / UNVERIFIED** |
| Observed | The mutation workspace explicitly refuses to generate a classification and labels source assertions as source fields. |
| Scientific assessment | This is ethically and scientifically appropriate. The platform is **not** a clinical decision-support system and must not be presented as one. |
| Required controls | If clinical use is ever claimed: validated ACMG/AMP rules, transcript/assembly handling, phenotype/zygosity context, sign-out by a qualified professional, and regulatory review. None are present. |

---

## 6. Protein structure

### SV-12 — Experimental structure retrieval

| Field | Value |
|---|---|
| Input | PDB `1M17` (EGFR tyrosine kinase domain with erlotinib). |
| Observed | Title, X-ray method, resolution 2.6 Å, release 2002-09-04, PDB content retrieved. |
| Status | **PASS** |
| Scientific note | Retrieval is correct; the audit did not validate any downstream structural computation. |

### SV-13 — Predicted structure fallback

| Field | Value |
|---|---|
| Input | UniProt `P04637`. |
| Observed | AlphaFold `AF-P04637-F1-model_v6.cif` retrieved and marked as predicted. |
| Status | **PASS** |
| Scientific note | The source is labelled `alphafold`, not conflated with an experimental structure. pLDDT/PAE were not analyzed. |

### SV-14 — PDB search

| Field | Value |
|---|---|
| Observed | Product endpoint HTTP 404; documented RCSB search endpoint HTTP 200 with 323 entries for `P04637`. |
| Status | **FAIL** |
| Finding | F-06 |
| Scientific consequence | Structure search by accession cannot work, even though direct entry retrieval can. |

---

## 7. Molecular docking

### SV-15 — Docking engine identity

| Field | Value |
|---|---|
| Observation | With no external binary present, `_dock_internal` generates ligand poses by random rigid-body rotation. No physics-based search, no scoring-driven optimization, no receptor flexibility, no explicit water/protonation handling. |
| Environment check | `vina`, `smina`, `gnina`, `qvina2`, `qvina-w` — all NOT FOUND. |
| Status | **FAIL** |
| Finding | S-01 |
| Scientific assessment | This is not molecular docking. A random pose can be a legitimate *baseline* only if labelled as such and never reported in kcal/mol as a binding affinity. |

### SV-16 — Docking output interpretation

| Field | Value |
|---|---|
| Observation | Poses are accompanied by heuristic scores presented with energy-like units (kcal/mol). No calibration against a crystal pose, no redocking RMSD, no enrichment study, no affinity correlation. |
| Status | **FAIL** |
| Scientific consequence | A user could select a compound because of a number that has no demonstrated relationship to binding. This is a decision-safety issue, not merely a quality issue. |
| Required validation | Redock co-crystallized ligands into their receptors; report RMSD ≤ 2 Å success rate; benchmark against DUD-E or a documented set; calibrate scores against measured affinities. |

### SV-17 — Receptor/ligand preparation

| Field | Value |
|---|---|
| Status | **UNVERIFIED** |
| Observation | No evidence of systematic protonation, tautomer, charge, or missing-residue handling was established during the audit. |
| Scientific consequence | Even with a real docking binary, pose quality would depend on preparation that is not demonstrated. |

---

## 8. Scoring functions

### SV-18 — “Vina” scoring

| Field | Value |
|---|---|
| Observation | `VinaScoringFunction` is a simplified implementation, not AutoDock Vina. It is presented under the Vina name. |
| Status | **FAIL** |
| Finding | S-02 |
| Scientific assessment | Naming an approximation after a validated scoring function misleads users about its provenance and accuracy. |

### SV-19 — “RF-Score” / “NNScore”

| Field | Value |
|---|---|
| Observation | Implementations are simplified approximations, not the published trained models. |
| Status | **FAIL** |
| Scientific consequence | No published performance can be attributed to these outputs. |

### SV-20 — MM/GBSA

| Field | Value |
|---|---|
| Observation | The MM/GBSA path returns `0.0` for the GB energy term. |
| Status | **FAIL** |
| Scientific assessment | A zero GB term means the reported binding energy is not a physically meaningful MM/GBSA estimate. Reporting it as such is invalid. |

---

## 9. Drug-target prediction

### SV-21 — End-to-end prediction

| Field | Value |
|---|---|
| Observed | `ImportError: RDKit is required for molecular feature calculation` with RDKit 2026.9.1 installed. |
| Status | **FAIL** |
| Finding | F-01 |
| Scientific consequence | No prediction can be produced, so no scientific claim can be attached to the feature. |

### SV-22 — Feature schema consistency

| Field | Value |
|---|---|
| Observed | With a compatibility shim, model expects 2,076 features; inference supplies 2,080 (`X has 2080 features, but SimpleImputer is expecting 2076 features`). |
| Status | **FAIL** |
| Finding | F-02 |
| Scientific consequence | Even after the import fix, the model and featurizer are not the same contract. Any “prediction” would require silent truncation/padding, which would invalidate it. |

### SV-23 — Demo model validity

| Field | Value |
|---|---|
| Observed | 20 samples; positives are drug-like compounds; negatives are short alkanes; train accuracy 0.95; train AUC 1.00; no held-out test. |
| Status | **FAIL** |
| Finding | S-04 |
| Scientific assessment | The classifier can separate “drug-like vs alkane” by size/complexity alone. The reported AUC does not measure target–ligand interaction. |

### SV-24 — Applicability domain

| Field | Value |
|---|---|
| Status | **NOT PRESENT** |
| Observation | No applicability-domain check, confidence calibration, or out-of-distribution warning was found. |
| Scientific consequence | Predictions on novel chemotypes would be presented without any indication that they are outside the training manifold. |

---

## 10. ADMET prediction

### SV-25 — Model availability

| Field | Value |
|---|---|
| Observed | `create_sample_training_data()` returns `{}`; no trained ADMET models are loaded. |
| Status | **FAIL** |
| Finding | S-08 |
| Scientific consequence | Any “ADMET prediction” must be rule-based or unavailable; it cannot be a validated ML prediction. |

### SV-26 — Rule-based outputs

| Field | Value |
|---|---|
| Status | **PARTIAL / UNVERIFIED** |
| Observation | Rule-based physicochemical filters (e.g. Lipinski-like thresholds) can be legitimate heuristics, but they must be labelled as rules rather than model predictions. |
| Scientific consequence | Rule outputs are not equivalent to measured permeability, clearance, hERG, or hepatotoxicity. |

---

## 11. Drug safety and toxicity

### SV-27 — Training data provenance

| Field | Value |
|---|---|
| Observed | `create_synthetic_toxicity_data()` generates random/synthetic labels for training. |
| Status | **FAIL** |
| Finding | S-07 |
| Scientific consequence | A model trained on synthetic labels cannot support toxicity claims, even if its internal test metric is high. |

### SV-28 — “Pretrained” claims

| Field | Value |
|---|---|
| Status | **FAIL** |
| Observation | No toxicity model artefacts exist; the “pretrained” path is a placeholder. |
| Scientific consequence | Safety alerts must not be presented as validated predictions. |

---

## 12. Drug repurposing

### SV-29 — Evidence scoring

| Field | Value |
|---|---|
| Observation | Repurposing scores combine heuristic baselines and real retrieval where available; the pathway score is a fixed 0.5 placeholder. TTD integration is a placeholder. |
| Status | **PARTIAL** |
| Finding | S-09 |
| Scientific assessment | The pipeline can organize evidence, but the composite score is not a validated repurposing probability. The neutral 0.5 pathway score can change rankings without any biological basis. |

### SV-30 — Required validation for repurposing claims

| Field | Value |
|---|---|
| Status | **NOT DONE** |
| Required | Retrospective hit-rate against known indications; held-out drug–disease pairs; calibration of composite scores; sensitivity analysis showing the effect of the 0.5 placeholder; provenance for every evidence source. |

---

## 13. Biomarker discovery

### SV-31 — Methodology review

| Field | Value |
|---|---|
| Observation | Uses scikit-learn pipelines with train/test separation in places; feature selection and cross-validation are present. |
| Status | **PARTIAL** |
| Scientific assessment | The general methodology is recognizable, but no dataset is bundled and no result was reproduced. Without data, leakage control and multiple-testing correction cannot be verified. |

### SV-32 — Statistical validity

| Field | Value |
|---|---|
| Status | **UNVERIFIED** |
| Why | No biomarker result, confidence interval, permutation test, or independent cohort was available to inspect. |
| Risk | Biomarker discovery is highly prone to overfitting and batch effects; a UI that returns ranked features without these controls can produce publishable-looking but irreproducible results. |

---

## 14. Genomic intelligence and conservation

### SV-33 — Disease/gene association

| Field | Value |
|---|---|
| Observation | `disease_associator` methods return `[]` stubs for disease/GWAS/HPO association. |
| Status | **FAIL** |
| Finding | F-11 |
| Scientific consequence | The genomic intelligence layer cannot associate variants/genes with diseases using real evidence. |

### SV-34 — Conservation track

| Field | Value |
|---|---|
| Observation | The genome browser generates `np.random.beta(2, 5, 100)` and displays it as a PhastCons track. |
| Status | **FAIL** |
| Finding | S-05 |
| Scientific assessment | This is fabricated biological evidence. Random values can create false impressions of conserved vs variable regions. This must be removed or explicitly labelled “synthetic demo data”, not “PhastCons”. |

### SV-35 — GWAS Catalog

| Field | Value |
|---|---|
| Observation | Legacy REST API HTTP 410; no GWAS client module exists. |
| Status | **FAIL / ABSENT** |
| Scientific consequence | No real GWAS association evidence is available to the genomic layer. |

---

## 15. AI research intelligence and reporting

### SV-36 — Variant annotation in reports

| Field | Value |
|---|---|
| Observation | The report generator labels variant annotation as “simulated”. |
| Status | **FAIL** |
| Finding | S-10 |
| Scientific consequence | A report can contain simulated biological assertions alongside real data without a sufficiently prominent boundary. |

### SV-37 — Citation integrity

| Field | Value |
|---|---|
| Observation | A fabricated DOI `10.5281/zenodo.xxxxxx` appears in generated references. |
| Status | **FAIL** |
| Scientific consequence | Fabricated identifiers are a research-integrity violation. Every citation must resolve to a real record or be omitted. |

### SV-38 — Reproducibility of generated reports

| Field | Value |
|---|---|
| Status | **UNVERIFIED** |
| Observation | No manifest tying a report to input files, code version, parameters, database releases, and model versions was found. |
| Scientific consequence | A report cannot be independently regenerated from the artefact alone. |

---

## 16. Integrated precision pipeline

### SV-39 — Stage completeness

| Field | Value |
|---|---|
| Observation | Literature stage returns zero/placeholder results; ML toxicity stage is absent or placeholder; other stages mix real retrieval with heuristics. |
| Status | **FAIL** |
| Finding | F-13 |
| Scientific consequence | The pipeline’s end-to-end conclusion is not supported by all advertised stages. |

### SV-40 — Composite decision validity

| Field | Value |
|---|---|
| Status | **NOT VALIDATED** |
| Observation | No weighting justification, calibration, or external comparison for the composite score was found. |
| Scientific consequence | The final ranking should not be used for prioritization decisions. |

---

## 17. Disease, pathway, and network analysis

### SV-41 — Network construction

| Field | Value |
|---|---|
| Observation | Disease/gene/pathway modules construct networks and retrieve pathway evidence in places, but several association methods are stubs and the pathway-repurposing score is fixed at 0.5. |
| Status | **PARTIAL** |
| Scientific assessment | Network visualization can be useful for exploration; it is not evidence of causal disease mechanism. |
| Required validation | Compare retrieved pathways with Reactome/QuickGO ground truth; test enrichment against a null model; report FDR; validate disease associations against ClinVar/Open Targets/GWAS. |

---

## 18. External data-source validation

| Source | Test | Observed | Scientific status |
|---|---|---|---|
| NCBI E-utilities (sequence) | `NM_007294.4`, `NM_000546.6` | Lengths 7,088 / 2,512 matched `slen` | **PASS** |
| NCBI PubMed | BRCA1 query | Real PMIDs 38030749, 41403285, 34081848 | **PASS** |
| ClinVar | `rs80357906` | `VCV000017677`, Pathogenic, expert panel | **PASS** |
| Ensembl REST `/overlap/region` | `17:7661779-7687538` | 12,807 variants; 2,055 ClinVar-annotated | **PASS** |
| Ensembl REST `/vcf/` | GRCh38 region | HTTP 404 | External endpoint issue |
| UniProt entry | `P04637` | Correct protein/sequence; wrong `entry_name` (`X02469`) | **PARTIAL** |
| UniProt mapping | GeneID 7157 | `{}`; retired endpoint returned HTML | **FAIL** |
| RCSB PDB entry | `1M17` | Correct metadata/content | **PASS** |
| RCSB PDB search | `P04637` | Code endpoint 404; documented endpoint 200/323 | **FAIL** |
| AlphaFold DB | `P04637` | `AF-P04637-F1-model_v6.cif` | **PASS** |
| ChEMBL molecule | `CHEMBL25` | ASPIRIN, correct SMILES | **PASS** |
| ChEMBL target | `CHEMBL203` | EGFR, UniProt `P00533` | **PASS** |
| ChEMBL bioactivities | `CHEMBL203` | Method does not exist | **FAIL** |
| Open Targets | TP53 | Product query HTTP 400; minimal query HTTP 200 | **FAIL** |
| GWAS Catalog | Associations | HTTP 410; no client module | **FAIL / ABSENT** |
| STRING | Network | Tests fail | **FAIL** (test evidence) |

---

## 19. Statistical and methodological validity

| Criterion | Observation | Status |
|---|---|---|
| Independent training/test split | Some pipelines split; DTI demo has no held-out test | **PARTIAL** |
| Cross-validation | Present in mutation ML, but standard deviations hardcoded to 0.0 | **FAIL** |
| Hyperparameter leakage | Search and reported CV use the same training data | **FAIL** |
| Multiple-testing correction | Not demonstrated in biomarker/pathway paths | **UNVERIFIED** |
| Confidence intervals | Not reported for model metrics | **UNVERIFIED / ABSENT** |
| Calibration | Claims not supported by reliability diagrams/Brier scores | **UNVERIFIED** |
| External validation | None | **ABSENT** |
| Applicability domain | None | **ABSENT** |
| Dataset provenance | No manifest/version pinning | **FAIL** |
| Model cards | None | **ABSENT** |
| Reproducibility seed control | Not demonstrated across ML paths | **UNVERIFIED** |

**Statistical conclusion:** the ML outputs do not meet the minimum evidence standard for scientific publication, regulatory submission, or clinical use. Internal accuracy/AUC values, where they exist, are training-set or demo values and should not be quoted as performance.

---

## 20. Reproducibility and provenance

| Requirement | Observation | Status |
|---|---|---|
| Code version captured with result | No | **FAIL** |
| Input file checksums | Not consistently captured | **FAIL** |
| Database release/version captured | Not consistently captured | **FAIL** |
| Model version/artefact hash | No artefacts exist | **FAIL** |
| Parameter capture | Partial/ad hoc | **PARTIAL** |
| Environment lockfile | No verified lockfile | **FAIL** |
| Deterministic seeds | Not demonstrated | **UNVERIFIED** |
| End-to-end workflow manifest | No | **FAIL** |

**Consequence:** none of the modelling outputs can be independently regenerated from a stored analysis record alone. This violates a basic reproducibility requirement for research software.

---

## 21. Claims versus evidence

| Project claim | Evidence found | Verdict |
|---|---|---|
| “Phase 1 100% complete” | Sequence/VCF/PubMed/lab/report engines work; Lab page not in sidebar | **PARTIAL** |
| “Phase 2 100% complete” | Real/crafted VCF, gzip, streaming, malformed handling pass | **PASS** |
| “Phase 3 100% complete” | Evidence-preserving mutation UI passes | **PASS** |
| “Phase 4 95% complete” | DTI broken; four external clients broken; docking heuristic; ADMET/safety untrained | **FAIL** |
| “Phase 5 90% complete” | Security primitives exist; 28 cloud + 27 multi-agent tests fail; most modules unreachable | **PARTIAL / FAIL** |
| “Phase 6 50% complete” | Genomic associator stubs; random conservation; lab/data/QA gaps | **FAIL** for claimed parts |
| “Phase 7 60% complete” | No deployment/health/backup evidence; unsafe API defaults | **UNVERIFIED / FAIL** |
| “AI drug discovery platform” | No trained models; no validated docking; fabricated report content | **NOT SUPPORTED** |
| “Production-ready” | No auth gate; hardcoded key; open bind; 21.3% test failure | **NOT SUPPORTED** |

---

## 22. Unverified register

The following could not be scientifically validated and must not be described as working:

| ID | Item | Why unverified | What would validate it |
|---|---|---|---|
| UV-01 | ORF/translation correctness | No RefSeq CDS/protein comparison | Compare with annotated CDS/protein; test all frames/strands |
| UV-02 | FASTQ quality metrics | No real FASTQ run | Benchmark against FastQC on a documented file |
| UV-03 | VCF REF/normalization | No reference FASTA | `bcftools norm` concordance on GRCh38 |
| UV-04 | ADMET predictions | No models/data | Train on curated assay data; external test set; calibration |
| UV-05 | Drug safety predictions | Synthetic labels only | Curated tox datasets; prospective validation |
| UV-06 | DTI performance | No artefacts; broken contract | Curated interaction dataset; time/split; external test |
| UV-07 | Docking accuracy | No docking engine; no redocking | Redocking RMSD; enrichment; affinity correlation |
| UV-08 | MM/GBSA | GB term zero | Compare with established MM/GBSA implementation |
| UV-09 | Biomarker performance | No dataset/result | Independent cohort; pre-registered pipeline |
| UV-10 | Repurposing hit rate | Heuristic/placeholder scores | Retrospective/retrospective-prospective validation |
| UV-11 | Integrated precision decisions | Placeholder stages | Complete stages; external validation; calibration |
| UV-12 | LLM/agent outputs | No LLM key; simulated content | Deterministic evaluation set; citation verification |
| UV-13 | Clinical utility | No clinical validation/regulatory review | Prospective clinical study; ACMG compliance; QMS |
| UV-14 | Cloud/deployment reliability | No credentials/deployment | Staged deployment; load/failover tests |
| UV-15 | Security exploitability | Static review only | Authorized penetration test |

---

## 23. Scientific readiness conclusion

**Ready for supervised exploration of sequence and VCF data. Not ready for research conclusions in drug discovery, ADMET, safety, docking, repurposing, biomarker, genomic-association, or precision-medicine workflows.**

The scientifically defensible core is narrow but real:

- Parse a FASTA and report length/GC.
- Parse a VCF and report alleles/genotypes without inventing annotation.
- Retrieve ClinVar/PubMed records with source fidelity.
- Retrieve PDB/AlphaFold structures.
- Store lab samples and generate a template report.

Everything that produces a *prediction*, *rank*, *score*, *energy*, *conservation value*, *toxicity call*, or *repurposing candidate* requires either replacement or explicit relabelling as an unvalidated heuristic. Fabricated or simulated biological content (random PhastCons, synthetic toxicity labels, fake DOI, simulated annotation) must be removed before any external use.

The remediation order is in `Priority_Improvement_Roadmap.md`; model-specific evidence is in `ML_Model_Audit_Report.md`.

---

*End of Scientific Validation Report.*
