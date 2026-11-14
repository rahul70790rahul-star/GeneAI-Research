# GeneAI Research

[![CI/CD](https://github.com/geneai/geneai-research/workflows/CI/CD/badge.svg)](https://github.com/geneai/geneai-research/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.57+-red.svg)](https://streamlit.io)

**GeneAI Research** is a comprehensive, AI-powered biotechnology research platform built with Streamlit. It provides integrated tools for sequence analysis, variant interpretation, drug discovery, ADMET prediction, biomarker discovery, multi-agent AI research assistance, cloud computing integration, and secure multi-user collaboration.

## Features

### Core Research Modules
- **Sequence Analysis** - DNA, RNA, and protein sequence analysis with FASTA/FASTQ support
- **VCF Analysis** - Variant call format parsing and filtering
- **Literature Search** - PubMed integration for research paper retrieval
- **Lab Sample Management** - Sample tracking and metadata

### Drug Discovery (Phases 4.3-4.8)
- **Disease Analysis** - Disease-gene associations and pathway analysis
- **Gene Identification** - Target gene discovery and prioritization
- **Mutation-to-Target** - Variant interpretation and target mapping
- **Protein Target Identification** - Protein structure and function analysis
- **Pathway Analysis** - Biological pathway enrichment and visualization
- **Protein Interaction Networks** - PPI network analysis and visualization
- **Druggability Analysis** - Target druggability assessment
- **Target Ranking** - Multi-criteria target prioritization
- **Protein Structure Analysis** - 3D structure visualization and analysis

### Advanced Analytics (Phases 4.9-4.13)
- **ADMET Prediction** - Absorption, Distribution, Metabolism, Excretion, Toxicity
- **Disease-Gene-Pathway Networks** - Integrated network analysis
- **Drug Safety & Toxicity** - Comprehensive safety profiling
- **Integrated Precision Drug Discovery** - End-to-end drug discovery workflows
- **AI Research Intelligence** - Knowledge graphs, mutation-to-drug workflows, AI candidate ranking

### AI-Powered Research (Phase 5)
- **Biotech Research Assistant** - Evidence-grounded Q&A with citations
- **Multi-Agent AI System** - Specialized agents for gene, protein, drug, disease analysis
- **Unified Knowledge Database** - Integrated biological data warehouse
- **Research Automation** - Scheduled and event-driven workflow automation
- **Multi-User Platform** - Authentication, teams, projects, permissions
- **REST API** - Programmatic access with authentication and rate limiting
- **Professional UI** - Theming, accessibility, responsive design
- **Security & Privacy** - Encryption, audit logging, access control, data anonymization
- **Cloud Integration** - Multi-cloud storage, compute, and batch processing
- **Performance Optimization** - Caching, monitoring, query optimization, resource pooling

## Quick Start

### Prerequisites
- Python 3.11+
- Docker (optional, for containerized deployment)

### Local Development

```bash
# Clone repository
git clone https://github.com/geneai/geneai-research.git
cd geneai-research

# Install dependencies
make install-dev

# Run tests
make test

# Start application
make run
```

The application will be available at `http://localhost:8501`.

### Docker Deployment

```bash
# Build image
make build

# Start services (includes PostgreSQL, Redis, Nginx)
make up

# View logs
make logs
```

### Configuration

Copy the example environment file and customize:

```bash
cp .env.example .env.staging
# Edit .env.staging with your values
```

## Project Structure

```
geneai-research/
├── app.py                      # Streamlit entry point
├── run_tests.py                # Test runner script
├── Makefile                    # Common development tasks
├── pyproject.toml              # Project configuration
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Multi-stage Docker build
├── docker-compose.yml          # Local development stack
├── docker-compose.staging.yml  # Staging environment
├── docker-compose.production.yml # Production environment
├── .github/workflows/          # CI/CD pipelines
├── scripts/                    # Deployment scripts
├── nginx/                      # Nginx configurations
├── geneai/                     # Core package
│   ├── __init__.py             # Package exports
│   ├── performance/            # Phase 5.10 - Performance optimization
│   ├── cloud_integration/      # Phase 5.6 - Cloud computing
│   ├── biotech_assistant/      # Phase 5.1 - AI research assistant
│   ├── multi_agent/            # Phase 5.2 - Multi-agent system
│   ├── unified_knowledge/      # Phase 5.3 - Knowledge database
│   ├── research_automation/    # Phase 5.4 - Workflow automation
│   ├── multi_user/             # Phase 5.5 - Multi-user platform
│   ├── rest_api/               # Phase 5.7 - REST API
│   ├── professional_ui/        # Phase 5.8 - Professional UI
│   ├── security/               # Phase 5.9 - Security & privacy
│   └── ...                     # Phases 4.x modules
├── tests/                      # Test suite
│   ├── test_*.py               # Module-specific tests
│   ├── test_integration.py     # Integration tests
│   └── test_smoke.py           # Import smoke tests
└── docs/                       # Documentation
```

## Testing

```bash
# Run all tests
make test

# Run specific test suites
make test-unit          # Unit tests only
make test-integration   # Integration tests
make test-smoke         # Smoke tests
make test-coverage      # With coverage report

# Run specific module tests
python -m pytest tests/test_performance.py -v
python -m pytest tests/test_cloud_integration.py -v
python -m pytest tests/test_biotech_assistant.py -v
```

## Code Quality

```bash
# Run all checks
make check

# Individual checks
make lint          # Ruff linting
make format        # Auto-format code
make typecheck     # MyPy type checking
make security-audit # Bandit + Safety
```

## Deployment

### Staging
```bash
make deploy-staging
# Or manually:
./scripts/deploy.sh -e staging
```

### Production
```bash
make deploy-prod
# Or manually:
./scripts/deploy.sh -e production
```

### Rollback
```bash
./scripts/deploy.sh -e staging -a rollback
./scripts/deploy.sh -e production -a rollback
```

## API Usage

The REST API is available at `/api/v1/` when deployed. Key endpoints:

```bash
# Health check
curl https://api.geneai.research/health

# Gene analysis
curl -H "Authorization: Bearer YOUR_API_KEY" \
     https://api.geneai.research/api/v1/genes/TP53

# ADMET prediction
curl -X POST -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"smiles": "CC(=O)OC1=CC=CC=C1C(=O)O"}' \
     https://api.geneai.research/api/v1/predict/admet
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and checks (`make check`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Citation

If you use GeneAI Research in your work, please cite:

```bibtex
@software{geneai2024,
  title = {GeneAI Research: AI-Powered Biotechnology Research Platform},
  author = {GeneAI Research Team},
  year = {2024},
  url = {https://github.com/geneai/geneai-research}
}
```

## Support

- **Issues**: [GitHub Issues](https://github.com/geneai/geneai-research/issues)
- **Discussions**: [GitHub Discussions](https://github.com/geneai/geneai-research/discussions)
- **Email**: research@geneai.example.com

## Roadmap

- [ ] Phase 5.11 - Comprehensive Testing & QA
- [ ] Phase 5.12 - Production Deployment & DevOps
- [ ] GraphQL API support
- [ ] Real-time collaboration features
- [ ] Advanced ML model training pipeline
- [ ] Federated learning integration