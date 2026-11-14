# GeneAI Research — Functional Test Report

**Audit date:** 2026-11-13  
**Project:** GeneAI Research, Phases 1–7  
**Repository:** `C:\Users\rahul\Documents\GeneAI_Research`  
**Test type:** Read-only functional, integration, API-contract, database, UI, and test-suite verification  
**Companion documents:** `Complete_Audit_Report.md`, `Scientific_Validation_Report.md`, `ML_Model_Audit_Report.md`, `Missing_Features_Report.md`, `Priority_Improvement_Roadmap.md`

> **Evidence rule:** every `PASS` below was produced by executing the described test and observing the stated output. Behaviour inferred only from reading source is labelled `STATIC`. Anything that could not be exercised is `UNVERIFIED`. No result was inferred from the project’s own status documents.

---

## 1. Executive result

| Metric | Result |
|---|---|
| Test cases executed | 51 |
| PASS | 22 |
| FAIL | 22 |
| PARTIAL | 2 |
| UNVERIFIED | 5 |
| Full pytest suite | **502 collected — 395 passed, 107 failed, 0 skipped in 445.55 s** |
| Streamlit boot | PASS on `http://127.0.0.1:8601` |
| Most severe functional defect | Drug-Target Prediction cannot run (RDKit import incompatibility), then fails a feature-contract check even when shimmed |
| Most severe integration defect | Open Targets, PDB search, UniProt mapping, and ChEMBL training paths are broken |
| Most severe product-honesty defect | Dashboard metrics and activity are fabricated; 21 implemented modules have no sidebar route |

### 1.1 Status counts by area

| Area | PASS | PARTIAL | FAIL | UNVERIFIED |
|---|---:|---:|---:|---:|
| Application shell and navigation | 2 | 0 | 4 | 0 |
| Sequence analysis | 3 | 1 | 0 | 2 |
| VCF analysis | 7 | 0 | 0 | 1 |
| Mutation interpretation | 2 | 0 | 0 | 0 |
| Clinical/literature retrieval | 2 | 1 | 2 | 0 |
| Laboratory and reports | 2 | 0 | 1 | 0 |
| Drug-target prediction | 1 | 0 | 4 | 0 |
| External drug/protein APIs | 2 | 0 | 3 | 0 |
| Database and performance | 0 | 0 | 5 | 0 |
| Security | 1 | 0 | 2 | 0 |
| Test suite and dependencies | 0 | 0 | 1 | 0 |
| Cloud/deployment | 0 | 0 | 0 | 2 |

---

## 2. Environment and isolation

| Item | Value |
|---|---|
| OS / shell | Windows, PowerShell |
| Python | 3.15.2 |
| Streamlit | 1.67.0 |
| pandas | 3.1.1 |
| NumPy | 2.5.4 |
| scikit-learn | 1.9.1 |
| RDKit | 2026.9.1 |
| PyTorch | 2.15.0 |
| App URL | `http://127.0.0.1:8601` |
| Test data root | `%TEMP%\geneai_audit_data` |
| Audit scripts | `%TEMP%\geneai_audit_scripts` |
| Raw pytest log | `%TEMP%\geneai_audit_pytest.txt` |
| Parsed failures | `%TEMP%\geneai_audit_pytest_parsed.json` |
| Real-data evidence | `%TEMP%\geneai_audit_realdata.json` |
| API evidence | `%TEMP%\geneai_audit_apis.json` |

**Isolation controls applied before any database-touching test**

```powershell
$env:GENEAI_DATA_DIR       = "$env:TEMP\geneai_audit_data"
$env:GENEAI_DATABASE_PATH  = "$env:TEMP\geneai_audit_data\geneai_audit.db"
python -m streamlit run app.py --server.port 8601
```

No project source file, project database, bundled dataset, or configuration file was edited. The only workspace writes were the audit reports and temporary Playwright upload fixtures under `.playwright-mcp\upload_fixtures\`, which were removed after testing.

**Networking note:** all live API checks used `requests` with `certifi`. Python’s `urllib` failed TLS verification against NCBI/Ensembl in this environment because of a corporate intercepting certificate. This is an environment property, not a product finding.

---

## 3. Test method

1. **Static route inventory** of `app.py`: counted sidebar entries, routed pages, fall-through branches, and placeholder functions.
2. **Unit/integration suite** executed with the isolated environment.
3. **Direct module execution** for parsers, clients, ML paths, lab DB, and report builder using small audit scripts in `%TEMP%`.
4. **Live API contract checks** with real public accessions/regions and recorded HTTP status codes.
5. **Browser-driven UI checks** using Playwright against the running Streamlit app, including file uploads.
6. **Negative tests** with malformed FASTA/VCF/JSON and missing optional dependencies.
7. **Reproduction of suspected defects** outside the test suite, so a failure could not be blamed on test debt alone.

### 3.1 Test type legend

| Type | Meaning |
|---|---|
| `EXECUTED` | Ran the product code and observed the result. |
| `LIVE API` | Called the real external service over HTTPS. |
| `UI` | Exercised through the running Streamlit app in a browser. |
| `DB` | Wrote to/read from an isolated SQLite database. |
| `STATIC` | Source inspection only; no runtime claim. |

---

## 4. Application shell and navigation

### FT-01 — Application boot

| Field | Value |
|---|---|
| Type | EXECUTED |
| Objective | Confirm the Streamlit entry point starts with isolated data paths. |
| Command | `python -m streamlit run app.py --server.port 8601` |
| Expected | Server starts; initial page renders; no fatal import error. |
| Observed | Server served `http://127.0.0.1:8601`; Overview rendered; no startup exception in the audit log. |
| Status | **PASS** |
| Notes | Log at `%TEMP%\geneai_audit_streamlit.log`. |

### FT-02 — Overview page render

| Field | Value |
|---|---|
| Type | UI |
| Objective | Confirm the default route renders after boot. |
| Steps | Open `http://127.0.0.1:8601`; wait for rerun. |
| Expected | Overview shell with sidebar and page content. |
| Observed | Overview rendered; sidebar contained 28 entries in seven categories. |
| Status | **PASS** (render only) |
| Notes | The *content* of the Overview is separately FAIL at FT-31. |

### FT-03 — Sidebar entries without routes

| Field | Value |
|---|---|
| Type | UI + STATIC |
| Objective | Verify every sidebar entry has a dedicated implementation. |
| Steps | Click “Disease-Associated Genes”; click “Mutation Analysis”; compare selected label with rendered heading. |
| Expected | A page specific to the selected feature. |
| Observed | Both selections silently rendered the Overview dashboard. `app.py` has no matching `elif` branch, so routing falls through to `render_main_dashboard()`. |
| Status | **FAIL** |
| Finding | F-08 |
| Impact | Users believe they are viewing a disease/mutation page when they are viewing unrelated dashboard content. |

### FT-04 — Placeholder pages

| Field | Value |
|---|---|
| Type | UI + STATIC |
| Objective | Determine whether sidebar entries labelled as features are implemented. |
| Entries tested | Research Projects, Recent Activities, Research Papers, Research Dashboard, Saved Results, Analysis Statistics. |
| Expected | Functional content. |
| Observed | Caption/“coming soon” content only. |
| Status | **FAIL** |
| Finding | F-09 |
| Impact | Inflates apparent feature coverage. |

### FT-05 — Unreachable implemented modules

| Field | Value |
|---|---|
| Type | STATIC |
| Objective | Identify implemented pages that cannot be reached from the sidebar. |
| Method | Enumerated route branches in `app.py`; compared with `NAV_CATEGORIES`. |
| Observed | 21 implemented module areas have routes but no sidebar entry, including Mutation ML Dashboard, Autonomous Bioinformatics Agent, Genomic Intelligence, Protein Intelligence, Drug Design, Molecular Docking, ADMET, Drug Safety, Integrated Precision, AI Research Intelligence, Biotech Assistant, Multi-Agent System, Unified Knowledge, Research Automation, Multi-User Platform, Cloud Integration, and REST API. |
| Status | **FAIL** |
| Finding | F-10 |
| Impact | The majority of Phase 4–7 functionality is invisible to a normal user. |

### FT-06 — Dashboard metrics and activity

| Field | Value |
|---|---|
| Type | UI + STATIC |
| Objective | Verify dashboard metrics derive from stored state. |
| Observed | `app.py` renders `active_projects + 3`, `completed + 5`, `active_projects + 2`, a hardcoded “+2 this week”, and five hardcoded activity entries. The UI displayed these values. |
| Status | **FAIL** |
| Finding | F-14 |
| Impact | Fabricated activity is indistinguishable from real activity to a new user. |

---

## 5. Sequence analysis

### FT-07 — Real BRCA1 FASTA via NCBI

| Field | Value |
|---|---|
| Type | EXECUTED + LIVE API |
| Objective | Validate parsing, length, GC content, and ambiguous-base count against an authoritative record. |
| Input | NCBI `NM_007294.4` (BRCA1), fetched over HTTPS. |
| Expected | Length equals NCBI `slen`; GC computed from sequence; ambiguous count reported. |
| Observed | HTTP 200; `slen=7088`; parsed length `7088`; GC `41.77%`; ambiguous count `0`. |
| Status | **PASS** |
| Finding | — |
| Evidence | `%TEMP%\geneai_audit_realdata.json` → `fasta_ncbi.NM_007294.4` |

### FT-08 — Real TP53 FASTA via NCBI

| Field | Value |
|---|---|
| Type | EXECUTED + LIVE API |
| Objective | Repeat sequence validation on an independent record. |
| Input | NCBI `NM_000546.6` (TP53). |
| Expected | Length equals NCBI `slen`; GC computed. |
| Observed | HTTP 200; `slen=2512`; parsed length `2512`; GC `53.38%`. |
| Status | **PASS** |
| Evidence | `%TEMP%\geneai_audit_realdata.json` → `fasta_ncbi.NM_000546.6` |

### FT-09 — Sequence analysis through the UI

| Field | Value |
|---|---|
| Type | UI |
| Objective | Confirm the browser path produces the same result as the module. |
| Steps | Open Basic Bioinformatics → Sequence Analysis; upload the BRCA1 FASTA; run analysis. |
| Expected | 7,088 bp; 41.77% GC; 0 ambiguous bases. |
| Observed | 7,088 bp; 41.77% GC; 0 ambiguous bases. |
| Status | **PASS** |
| Notes | The page displayed ORF/translation panels; their biological correctness was not independently validated (see FT-11). |

### FT-10 — Malformed FASTA/FASTQ rejection

| Field | Value |
|---|---|
| Type | EXECUTED |
| Objective | Confirm malformed records produce clear errors rather than fabricated results. |
| Inputs | Empty file; FASTA header with no sequence; empty FASTA header; data before a later `>` header; FASTQ with sequence/quality length mismatch. |
| Expected | Rejection with a readable message for every malformed case. |
| Observed | Empty → `The uploaded file is empty.`; no sequence → `FASTA record 'seq1' has no sequence.`; empty header → `FASTA header is empty.`; FASTQ mismatch → `FASTQ sequence and quality lengths differ near line 1.` **However**, a file whose first line is raw sequence and whose later line starts with `>` is accepted as a raw sequence (`ACGT>SEQ1ACGT`), embedding the `>` character. |
| Status | **PARTIAL** |
| Observation | O-01 (LOW) — raw-sequence fallback does not reject embedded `>`/`@` markers. |
| Notes | The common malformed cases are handled well. The edge case should be fixed by rejecting `>`/`@` inside raw sequence content or by requiring an explicit “raw sequence” mode. |

### FT-11 — ORF and translation correctness

| Field | Value |
|---|---|
| Type | UNVERIFIED |
| Objective | Validate ORF coordinates and translated protein against a reference annotation. |
| Why not executed | No reference CDS/protein mapping was established for the tested transcripts within the audit window; the UI exposes ORFs but the audit did not validate them against RefSeq protein records. |
| Status | **UNVERIFIED** |
| Finding | — |

### FT-12 — FASTQ end-to-end quality analysis

| Field | Value |
|---|---|
| Type | UNVERIFIED |
| Objective | Validate FASTQ parsing and quality metrics with a real instrument file. |
| Why not executed | No real FASTQ was exercised end-to-end during this audit. Source contains FASTQ handling, but no runtime result is claimed. |
| Status | **UNVERIFIED** |
| Finding | — |

---

## 6. VCF analysis

### FT-13 — Real vcflib VCF parse

| Field | Value |
|---|---|
| Type | EXECUTED + LIVE API |
| Objective | Parse an independently maintained VCF and reconcile records/alleles. |
| Input | vcflib `sample.vcf`, 2,050 bytes, HTTP 200. |
| Expected | 9 data rows; multiallelic rows expand; dot-ALT rows skipped. |
| Observed | 9 data rows → 10 alleles; 6 SNP, 4 INDEL; 3 multiallelic rows; 2 dot-ALT rows skipped. |
| Status | **PASS** |
| Evidence | `%TEMP%\geneai_audit_vcf_real.json` |

### FT-14 — Gzip round-trip

| Field | Value |
|---|---|
| Type | EXECUTED |
| Objective | Confirm compressed input yields identical alleles. |
| Observed | 924-byte gzip → 10 alleles; `same_as_plain=true`. |
| Status | **PASS** |

### FT-15 — Streaming summary and genotype metrics

| Field | Value |
|---|---|
| Type | EXECUTED |
| Objective | Verify streaming interpretation, per-sample genotype counts, and QUAL statistics. |
| Observed | 10 variant records from 9 source rows; chromosomes 19/20/X; genotype counts `HOM_REF=9, HET=12, HOM_ALT=3, OTHER_ALT=6`; 3 samples; mean QUAL `30.56` (min 3.0, max 67.0); 0 duplicate alleles. |
| Status | **PASS** |
| Notes | The summary correctly states that REF validation and indel normalization were **not** verified without a reference FASTA. |

### FT-16 — Malformed VCF rejection

| Field | Value |
|---|---|
| Type | EXECUTED + UI |
| Objective | Confirm invalid input fails clearly. |
| Cases | Missing `#CHROM`; bad first eight columns; invalid coordinate; empty ALT; wrong field count; empty file. |
| Observed | All six rejected with specific messages, e.g. `ValueError: Invalid coordinate at VCF line 4.` The UI showed “Invalid coordinate at VCF line 3.” for its fixture. |
| Status | **PASS** |

### FT-17 — Crafted variant classes

| Field | Value |
|---|---|
| Type | EXECUTED |
| Objective | Validate classification of SNV, insertion, deletion, MNV/complex, multiallelic, symbolic `<DEL>`, and `*` allele. |
| Observed | SNV→`SNP`; insertion/deletion→`INDEL`; `CA→TG`→`COMPLEX`; multiallelic expanded to two SNPs; `<DEL>`→`SYMBOLIC`; `*`→`SYMBOLIC`. |
| Status | **PASS** |
| Evidence | `%TEMP%\geneai_audit_realdata.json` → `vcf_crafted` |

### FT-18 — VCF dot-ALT handling

| Field | Value |
|---|---|
| Type | EXECUTED |
| Objective | Confirm rows with ALT `.` are skipped rather than mis-parsed. |
| Observed | 2 dot-ALT rows skipped; 9 source rows still produced 10 alleles from the remaining rows. |
| Status | **PASS** |

### FT-19 — Reference-based normalization

| Field | Value |
|---|---|
| Type | UNVERIFIED |
| Objective | Validate REF alleles and left-normalize indels against GRCh38. |
| Why not executed | The product explicitly requires a reference FASTA for this; no reference FASTA was configured during the audit. The UI states this limitation. |
| Status | **UNVERIFIED** (and honestly disclosed by the product) |
| Finding | — |

### FT-20 — Ensembl VCF endpoint

| Field | Value |
|---|---|
| Type | LIVE API |
| Objective | Retrieve a real VCF region for validation. |
| Observed | Ensembl REST `/vcf/` returned HTTP 404 for the GRCh38 TP53 region. `/overlap/region/17:7661779-7687538` returned 12,807 variants, 2,055 ClinVar-annotated. The product does not depend on the failing `/vcf/` endpoint for its parser. |
| Status | **PASS** (alternative endpoint) |
| Notes | The 404 is an external API-version issue, not a parser defect. |

---

## 7. Mutation interpretation

### FT-21 — UI scan of the real VCF

| Field | Value |
|---|---|
| Type | UI + EXECUTED |
| Objective | Confirm the mutation workspace interprets evidence without inventing classifications. |
| Steps | Open AI Mutation Interpretation; upload vcflib `sample.vcf`; run. |
| Expected | Variant/sample counts consistent with parsing; no pathogenicity classification. |
| Observed | 9 source rows → 10 alleles; 3 samples; mean QUAL 30.56; embedded annotation counts all zero; explicit text: “No classification generated.” |
| Status | **PASS** |
| Finding | — |

### FT-22 — Classification honesty

| Field | Value |
|---|---|
| Type | UI + STATIC |
| Objective | Ensure the module does not present a clinical classification it cannot support. |
| Observed | The UI displays source assertions as source fields and refuses to generate a classification; the engine documents that reference FASTA is required for REF validation. |
| Status | **PASS** |
| Finding | — |

---

## 8. Clinical and literature retrieval

### FT-23 — ClinVar lookup

| Field | Value |
|---|---|
| Type | EXECUTED + LIVE API |
| Objective | Verify accession, HGVS, classification, and review status. |
| Input | `rs80357906` (BRCA1 founder duplication). |
| Observed | HTTP 200; UID `17677`; accession `VCV000017677`; title `NM_007294.4(BRCA1):c.5266dup (p.Gln1756fs)`; germline classification **Pathogenic**; review status **reviewed by expert panel**; last evaluated 2016-04-22; GRCh38 `17:43057062-43057063`. |
| Status | **PASS** |
| Finding | — |
| Evidence | `%TEMP%\geneai_audit_realdata.json` → `clinvar.rs80357906` |

### FT-24 — PubMed search

| Field | Value |
|---|---|
| Type | EXECUTED + LIVE API |
| Objective | Confirm real literature retrieval. |
| Query | `BRCA1 pathogenic variant`, limit 3. |
| Observed | Real PMIDs 38030749, 41403285, 34081848 with titles. |
| Status | **PASS** |
| Finding | — |

### FT-25 — Gene Identification lookup

| Field | Value |
|---|---|
| Type | UI + EXECUTED |
| Objective | Resolve a gene symbol to cross-database identifiers. |
| Steps | Open Gene Identification; query `TP53`. |
| Expected | Ensembl/UniProt/NCBI identifiers or a clear API error. |
| Observed | `NameError: name 'response' is not defined`, raw traceback. Root cause: `geneai/drug_discovery/api_clients.py:338` in `lookup_ensembl_symbols`. |
| Status | **FAIL** |
| Finding | F-03 |
| Impact | A core Phase 4 lookup feature is completely unusable. |

### FT-26 — UniProt entry retrieval

| Field | Value |
|---|---|
| Type | LIVE API |
| Objective | Verify accession, entry name, protein name, sequence length, and cross-references. |
| Input | `P04637` (TP53). |
| Expected | `P53_HUMAN`; 393 aa; 318 PDB entries; 116 GO terms; 47 pathways (values observed). |
| Observed | HTTP path worked; protein name “Cellular tumor antigen p53”; 393 aa; 318 PDB; 116 GO; 47 pathways **but** `entry_name` returned as `X02469` instead of `P53_HUMAN`. |
| Status | **PARTIAL** |
| Finding | F-07 |

### FT-27 — UniProt ID mapping

| Field | Value |
|---|---|
| Type | LIVE API |
| Objective | Map GeneID 7157 → UniProtKB. |
| Observed | `{}`. The retired `https://www.uniprot.org/uploadlists` endpoint returned HTML, not JSON. |
| Status | **FAIL** |
| Finding | F-07 |

---

## 9. Laboratory and reports

### FT-28 — Lab sample register

| Field | Value |
|---|---|
| Type | DB |
| Objective | Confirm isolated create/read and statistics. |
| Command | Audit script called `add_sample(name="AUDIT_SAMPLE_001", material="DNA", project="audit")` against `%TEMP%` DB. |
| Observed | Sample ID `GAR-49C8829DDB`; status `received`; `get_lab_stats()` reflected the new sample. |
| Status | **PASS** |
| Notes | The Lab Samples page is not present in the sidebar (navigation gap), but the data layer works. |

### FT-29 — Clinical-trial persistence

| Field | Value |
|---|---|
| Type | DB |
| Objective | Upsert and search a clinical trial. |
| Observed | `sqlite3.OperationalError: 26 values for 25 columns` on insert; the related search test fails for the same schema reason. |
| Status | **FAIL** |
| Finding | D-01 |
| Impact | Clinical-trial data cannot be persisted. |

### FT-30 — Report builder

| Field | Value |
|---|---|
| Type | EXECUTED |
| Objective | Confirm the report is honest about citations and provenance. |
| Observed | `build_report()` returned a template that explicitly states no citations are generated automatically and lists the limitation. |
| Status | **PASS** |
| Notes | The AI research report generator is separately FAIL at FT-45 because it contains simulated annotation and a fabricated DOI. |

---

## 10. Drug-target prediction

### FT-31 — Predictor instantiation with installed RDKit

| Field | Value |
|---|---|
| Type | EXECUTED + UI |
| Objective | Run the flagship DTI prediction end-to-end. |
| Input | ChEMBL molecule `CHEMBL25` (aspirin) and target `P00533` (EGFR). |
| Expected | A score/probability and model metadata. |
| Observed | UI: “RDKit is not installed” traceback. Module: `ImportError: RDKit is required for molecular feature calculation`. |
| Root cause | `molecular_descriptors.py` imports `rdMolDescriptors.CalcExactMW`; RDKit 2026.9.1 no longer exposes it, so the module sets `RDKIT_AVAILABLE=False`. The package **is** installed. |
| Status | **FAIL** |
| Finding | F-01 |
| Impact | The flagship Phase 4 feature is unusable. |

### FT-32 — Feature-contract reproduction with compatibility shim

| Field | Value |
|---|---|
| Type | EXECUTED (compatibility-shim experiment, clearly labelled) |
| Objective | Determine whether repairing the import alone makes prediction work. |
| Method | Monkeypatched the missing descriptor symbol in an isolated script; did not modify project files. |
| Observed | Model expects 2,076 features; inference supplies 4 target features, producing `ValueError: X has 2080 features, but SimpleImputer is expecting 2076 features as input.` Engine returned `success=False`. |
| Status | **FAIL** |
| Finding | F-02 |
| Notes | This is a synthetic repair experiment, not a product-mode result. It demonstrates that F-01 masks a second defect. |

### FT-33 — Built-in demo model quality

| Field | Value |
|---|---|
| Type | EXECUTED + STATIC |
| Objective | Assess the demo model’s scientific meaning. |
| Observed | Default demo model: 20 samples, train accuracy 0.95, train AUC 1.00. Positives are drug-like molecules; negatives are short alkanes. No held-out test. |
| Status | **FAIL** |
| Finding | S-04 |
| Notes | The high AUC reflects molecular size/complexity confounding, not target–ligand interaction. |

### FT-34 — ChEMBL molecule and target retrieval

| Field | Value |
|---|---|
| Type | LIVE API |
| Objective | Verify the non-training ChEMBL paths. |
| Observed | `CHEMBL25` → ASPIRIN, SMILES `CC(=O)Oc1ccccc1C(=O)O`, max phase 4.0; `CHEMBL203` → Epidermal growth factor receptor, UniProt `P00533`. |
| Status | **PASS** |

### FT-35 — ChEMBL training path

| Field | Value |
|---|---|
| Type | EXECUTED |
| Objective | Train a DTI model from ChEMBL bioactivities. |
| Observed | `AttributeError: module 'geneai.drug_discovery.chembl_client' has no attribute 'get_target_bioactivities'`; `prediction_engine.train_from_chembl` calls the missing method. |
| Status | **FAIL** |
| Finding | F-05 |
| Impact | The only advertised route to a real DTI training set is broken. |

---

## 11. External drug and protein APIs

### FT-36 — Open Targets client

| Field | Value |
|---|---|
| Type | LIVE API |
| Objective | Retrieve TP53 target data through the product client. |
| Observed | Product query → HTTP 400. A minimal hand-written GraphQL query to the same endpoint → HTTP 200 with `ENSG00000141510`, `TP53`, `tumor protein p53`. The failure is caused by removed fields such as `proteinIds.uniprot`, `tractability`, `associatedDiseasesCount`, and `knownDrugsCount`. |
| Status | **FAIL** |
| Finding | F-04 |

### FT-37 — PDB direct entry

| Field | Value |
|---|---|
| Type | LIVE API |
| Objective | Retrieve a known PDB entry. |
| Input | `1M17` (EGFR + erlotinib). |
| Observed | Title, organism, X-ray method, resolution 2.6 Å, release date 2002-09-04, PDB content retrieved. |
| Status | **PASS** |

### FT-38 — PDB search

| Field | Value |
|---|---|
| Type | LIVE API |
| Objective | Search PDB by UniProt accession. |
| Input | `P04637`. |
| Observed | Product endpoint `https://data.rcsb.org/rest/v1/core/search` → HTTP 404. Documented search endpoint `https://search.rcsb.org/rcsbsearch/v2/query` → HTTP 200 with 323 entries. |
| Status | **FAIL** |
| Finding | F-06 |

### FT-39 — AlphaFold fallback

| Field | Value |
|---|---|
| Type | LIVE API |
| Objective | Confirm predicted-structure fallback. |
| Input | `P04637`. |
| Observed | `AF-P04637-F1-model_v6.cif` retrieved; marked source `alphafold`; CIF content present. |
| Status | **PASS** |

### FT-40 — GWAS Catalog

| Field | Value |
|---|---|
| Type | LIVE API + STATIC |
| Objective | Retrieve disease–variant associations. |
| Observed | Legacy REST API returned HTTP 410; no GWAS Catalog client module exists in the package. |
| Status | **FAIL** |
| Finding | F-11 / missing feature MF-09 |

---

## 12. Database and performance

### FT-41 — Full test suite

| Field | Value |
|---|---|
| Type | EXECUTED |
| Command | `python -m pytest -q` with isolated data env. |
| Observed | **107 failed, 395 passed, 3 warnings in 445.55 s** (502 collected). |
| Status | **FAIL** |
| Finding | T-01 |
| Notes | Failure distribution and root causes are in `Complete_Audit_Report.md` §Q. |

### FT-42 — Unified-knowledge bulk insert

| Field | Value |
|---|---|
| Type | EXECUTED (pytest) |
| Expected | Under the 5.0 s budget. |
| Observed | 15.98 s. |
| Status | **FAIL** |
| Finding | P-01 |

### FT-43 — Unified-knowledge query

| Field | Value |
|---|---|
| Type | EXECUTED (pytest) |
| Expected | Under the 2.0 s budget. |
| Observed | 3.98 s. |
| Status | **FAIL** |
| Finding | P-02 |

### FT-44 — Cache layers

| Field | Value |
|---|---|
| Type | EXECUTED (pytest) |
| Observed | `MultiLevelCache` → `TypeError: expected str, bytes or os.PathLike object, not NoneType`; `AsyncCache.get()` → coroutine received by synchronous caller. |
| Status | **FAIL** |
| Finding | P-03 / P-04 |

### FT-45 — Query optimiser and resource pool

| Field | Value |
|---|---|
| Type | EXECUTED (pytest) |
| Observed | No index suggestion produced; complexity classified “medium” where the test expects “low”; pool statistics report 0 where 1 is expected. |
| Status | **FAIL** |
| Finding | P-05 |

---

## 13. Security

### FT-46 — REST API key and bind defaults

| Field | Value |
|---|---|
| Type | STATIC |
| Objective | Determine whether default credentials/network exposure are safe. |
| Observed | Hardcoded demo key `geneai_demo_key_12345` with read/write/analyze scopes; default bind `0.0.0.0:5000`; keys held in memory and hashed with plain SHA-256. |
| Status | **FAIL** (static finding) |
| Findings | SEC-01, SEC-02, SEC-03 |
| Notes | No REST API exploit was executed; the finding is established from source. |

### FT-47 — Application authentication gate

| Field | Value |
|---|---|
| Type | STATIC |
| Objective | Determine whether the Streamlit app enforces login. |
| Observed | No authentication check wraps the main app; the multi-user module exists but is not enforced at the entry point. |
| Status | **FAIL** (static finding) |
| Finding | SEC-04 |

### FT-48 — Password hashing primitives

| Field | Value |
|---|---|
| Type | STATIC |
| Objective | Assess stored-password protection. |
| Observed | PBKDF2-HMAC-SHA256, 200,000 iterations, per-user salt, `hmac.compare_digest`. |
| Status | **PASS** |
| Finding | — |

---

## 14. Dependencies, cloud, and deployment

### FT-49 — Optional ML dependencies

| Field | Value |
|---|---|
| Type | EXECUTED |
| Observed | Installed Optuna 5.0.0, SHAP 0.54.1, MLflow 3.18.0 are outside declared pins and fail to import because `colorlog`, `slicer`, and `yaml` are absent. Nine ML-enhancement tests fail. |
| Status | **FAIL** |
| Finding | D-04 |

### FT-50 — Cloud operations

| Field | Value |
|---|---|
| Type | UNVERIFIED |
| Why not executed | No AWS/GCP/Azure credentials; `boto3` and provider SDKs are not installed. |
| Static observation | 28 cloud tests fail on API drift (`LocalStorage(base_path=...)`, `CloudResourceManager(config)`, missing enum members). |
| Status | **UNVERIFIED** for live cloud behaviour; **FAIL** for local/cloud adapter contracts. |
| Finding | D-03 / D-04 |

### FT-51 — Deployment, health, monitoring, backup

| Field | Value |
|---|---|
| Type | UNVERIFIED |
| Why not executed | No Docker/Kubernetes deployment was run; no health endpoint or backup procedure was exercised. |
| Status | **UNVERIFIED** |
| Notes | Container/CI files may exist; existence is not evidence of working deployment. |

---

## 15. Test-case index

| ID | Test | Type | Status | Finding |
|---|---|---|---|---|
| FT-01 | Application boot | EXECUTED | PASS | — |
| FT-02 | Overview render | UI | PASS | — |
| FT-03 | Sidebar entries without routes | UI/STATIC | FAIL | F-08 |
| FT-04 | Placeholder pages | UI/STATIC | FAIL | F-09 |
| FT-05 | Unreachable implemented modules | STATIC | FAIL | F-10 |
| FT-06 | Fabricated dashboard | UI/STATIC | FAIL | F-14 |
| FT-07 | BRCA1 FASTA | EXECUTED/LIVE | PASS | — |
| FT-08 | TP53 FASTA | EXECUTED/LIVE | PASS | — |
| FT-09 | Sequence UI | UI | PASS | — |
| FT-10 | Malformed FASTA/FASTQ | EXECUTED | PARTIAL | O-01 |
| FT-11 | ORF/translation correctness | — | UNVERIFIED | — |
| FT-12 | FASTQ end-to-end | — | UNVERIFIED | — |
| FT-13 | Real VCF parse | EXECUTED/LIVE | PASS | — |
| FT-14 | VCF gzip round-trip | EXECUTED | PASS | — |
| FT-15 | VCF streaming metrics | EXECUTED | PASS | — |
| FT-16 | Malformed VCF | EXECUTED/UI | PASS | — |
| FT-17 | Crafted variant classes | EXECUTED | PASS | — |
| FT-18 | Dot-ALT handling | EXECUTED | PASS | — |
| FT-19 | Reference normalization | — | UNVERIFIED | — |
| FT-20 | Ensembl region retrieval | LIVE | PASS | — |
| FT-21 | Mutation UI scan | UI/EXECUTED | PASS | — |
| FT-22 | Classification honesty | UI/STATIC | PASS | — |
| FT-23 | ClinVar lookup | EXECUTED/LIVE | PASS | — |
| FT-24 | PubMed search | EXECUTED/LIVE | PASS | — |
| FT-25 | Gene Identification | UI/EXECUTED | FAIL | F-03 |
| FT-26 | UniProt entry | LIVE | PARTIAL | F-07 |
| FT-27 | UniProt mapping | LIVE | FAIL | F-07 |
| FT-28 | Lab sample register | DB | PASS | — |
| FT-29 | Clinical-trial persistence | DB | FAIL | D-01 |
| FT-30 | Report builder | EXECUTED | PASS | — |
| FT-31 | DTI with installed RDKit | EXECUTED/UI | FAIL | F-01 |
| FT-32 | DTI feature contract (shim) | EXECUTED | FAIL | F-02 |
| FT-33 | DTI demo quality | EXECUTED/STATIC | FAIL | S-04 |
| FT-34 | ChEMBL molecule/target | LIVE | PASS | — |
| FT-35 | ChEMBL training | EXECUTED | FAIL | F-05 |
| FT-36 | Open Targets client | LIVE | FAIL | F-04 |
| FT-37 | PDB entry | LIVE | PASS | — |
| FT-38 | PDB search | LIVE | FAIL | F-06 |
| FT-39 | AlphaFold fallback | LIVE | PASS | — |
| FT-40 | GWAS Catalog | LIVE/STATIC | FAIL | F-11 |
| FT-41 | Full pytest suite | EXECUTED | FAIL | T-01 |
| FT-42 | Bulk insert performance | EXECUTED | FAIL | P-01 |
| FT-43 | Query performance | EXECUTED | FAIL | P-02 |
| FT-44 | Cache layers | EXECUTED | FAIL | P-03/P-04 |
| FT-45 | Query optimiser/resource pool | EXECUTED | FAIL | P-05 |
| FT-46 | API key/bind defaults | STATIC | FAIL | SEC-01/02/03 |
| FT-47 | App auth gate | STATIC | FAIL | SEC-04 |
| FT-48 | Password hashing | STATIC | PASS | — |
| FT-49 | Optional ML dependencies | EXECUTED | FAIL | D-04 |
| FT-50 | Cloud operations | — | UNVERIFIED | D-03/D-04 |
| FT-51 | Deployment/health/backup | — | UNVERIFIED | — |

---

## 16. Actual tests versus theoretical recommendations

### 16.1 What was actually executed

- Full pytest suite (502 tests).
- Streamlit boot and browser interaction on port 8601.
- Real NCBI FASTA retrieval and parsing for two transcripts.
- Real vcflib VCF parsing, gzip round-trip, streaming, and six malformed-input cases.
- UI mutation scan with the real VCF.
- Live ClinVar and PubMed queries.
- Live UniProt entry and mapping calls.
- Live ChEMBL molecule/target calls and the failing training path.
- Live Open Targets minimal and product queries.
- Live PDB entry/search and AlphaFold fallback.
- Isolated lab DB insert/read and clinical-trial insert.
- DTI instantiation and the labelled compatibility-shim reproduction.
- Static review of routing, security defaults, docking/scoring, and ML training code.

### 16.2 What is a recommendation, not a test result

The following appear in the companion reports as remediation, not as verified behaviour:

- Replacing random-rotation docking with Vina/Smina/GNINA and re-scoring known complexes.
- Training DTI/ADMET/safety models on curated, split, provenance-tracked datasets.
- Adding authentication, RBAC, secret management, and a safe default bind.
- Replacing fabricated dashboard/report content with stored events and real citations.
- Building a reference-FASTA normalization pipeline.
- Adding CI contract tests for every external API.

No claim in this report depends on those recommendations having been implemented.

---

## 17. Coverage gaps and residual risk

| Gap | Consequence |
|---|---|
| No real FASTQ end-to-end test | FASTQ quality behaviour remains unproven. |
| No reference FASTA for VCF normalization | Indel normalization/REF validation remains unproven. |
| No ORF/protein reference comparison | Translation correctness remains unproven. |
| No cloud credentials | Cloud adapters are only statically/contract tested. |
| No Docker/Kubernetes run | Deployment claims remain unproven. |
| No external LLM key | LLM-dependent assistants were not exercised. |
| No licensed datasets (TTD, DrugBank) | Licensed-data features remain unproven. |
| No trained model artefacts | All model-performance claims remain unproven. |
| No penetration test | Security findings are source-level, not exploit-level. |

---

## 18. Functional conclusion

The Phase 1–3 workbench is genuinely functional for the tested paths: sequence parsing, VCF parsing/streaming, evidence-preserving mutation interpretation, ClinVar, PubMed, lab sample persistence, and report templating all behaved correctly against real data. Those components should be preserved.

The Phase 4–7 surface does not pass functional acceptance. The flagship predictor cannot run; several external clients cannot complete a request; the clinical-trial schema is broken; cache/performance contracts fail; the dashboard fabricates activity; and 21 implemented modules are unreachable. The 107/502 test failures are consistent with these observations rather than being an artefact of the audit environment.

**Functional readiness: research prototype, not production.** See `Priority_Improvement_Roadmap.md` for the repair order.

---

*End of Functional Test Report.*
