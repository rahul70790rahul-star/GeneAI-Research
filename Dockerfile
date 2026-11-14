# GeneAI Research - Multi-stage Dockerfile
# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r geneai && useradd -r -g geneai geneai

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/geneai/.local

# Copy application code
COPY --chown=geneai:geneai . .

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/uploads && chown -R geneai:geneai /app

# Switch to non-root user
USER geneai

# Add local packages to PATH
ENV PATH=/home/geneai/.local/bin:$PATH

# Expose port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]