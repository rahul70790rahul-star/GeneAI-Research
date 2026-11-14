# GeneAI Research - Production Secrets Configuration

## ✅ Secret Generation Verified

| Secret | Format | Length | Verification |
|--------|--------|--------|--------------|
| **SECRET_KEY** | URL-safe Base64 (token_urlsafe) | 43 chars (32 bytes entropy) | ✅ Valid |
| **ENCRYPTION_KEY** | Standard Base64 (b64encode) | 44 chars (32 bytes decoded) | ✅ Valid 32-byte key |

**Generated Example:**
```
SECRET_KEY=kcka2hZPLG3GdDYmUyoIuR3F4s13Q-7LpV0DtfZLNbQ
ENCRYPTION_KEY=HUAhsPD/HxNoy7eFrlD8SDb3BDe7iarECSftgHIPDMo=
```

> **Note:** ENCRYPTION_KEY uses standard Base64 (may contain `+` `/` `=`). This is correct for a 32-byte encryption key. URL-safe encoding is not required.

---

## 🔐 Streamlit Cloud Secrets Configuration

**Location:** Streamlit Community Cloud → Your App → Settings → Secrets

**Copy this TOML exactly, replacing placeholder values:**

```toml
# GeneAI Research - Streamlit Cloud Secrets
# NEVER commit this to GitHub!

[database]
# Neon PostgreSQL connection string (from Neon Console → Connection Details)
# Format: postgresql://user:password@ep-xxx.region.aws.neon.tech/dbname?sslmode=require
url = "postgresql://USER:PASSWORD@ep-XXX.us-east-1.aws.neon.tech/geneai?sslmode=require"
pool_size = 5
max_overflow = 10
pool_timeout = 30
pool_recycle = 1800

[redis]
# Upstash Redis REST API (from Upstash Console → REST API)
url = "https://XXX.upstash.io"
token = "YOUR_UPSTASH_REST_TOKEN"

[security]
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
secret_key = "YOUR_43_CHAR_SECRET_KEY_HERE"

# JWT Configuration
jwt_algorithm = "HS256"
jwt_expiration_hours = 24

# API Key prefix for REST API
api_key_prefix = "gai_"

# Generate with: python -c "import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
encryption_key = "YOUR_44_CHAR_BASE64_ENCRYPTION_KEY_HERE"

[external_apis]
# Optional - for enhanced features (get from respective platforms)
ncbi_api_key = ""
uniprot_api_key = ""
opentargets_api_key = ""
alphafold_api_key = ""
chemlb_api_key = ""

[app]
# Your Render FastAPI service URL (after deployment)
api_base_url = "https://geneai-api.onrender.com"

[features]
enable_multi_user = true
enable_rest_api = true
enable_cloud_integration = false
enable_advanced_analytics = true
enable_audit_logging = true
enable_mutation_ml = true

[ml_models]
model_dir = "data/models"
default_model = "best_mutation_model_real.pkl"
enable_shap = true

[performance]
cache_ttl_seconds = 300
max_concurrent_jobs = 5
worker_processes = 2
```

---

## ⚡ Render Environment Variables Configuration

**Location:** Render Dashboard → Your Web Service → Environment

**Add these as Environment Variables (not secret files):**

| Key | Value | Notes |
|-----|-------|-------|
| `PYTHON_VERSION` | `3.11` | |
| `ENVIRONMENT` | `production` | |
| `LOG_LEVEL` | `INFO` | |
| `DATABASE_URL` | `postgresql://USER:PASSWORD@ep-XXX.us-east-1.aws.neon.tech/geneai?sslmode=require` | **Same as Streamlit** |
| `UPSTASH_REDIS_REST_URL` | `https://XXX.upstash.io` | **Same as Streamlit** |
| `UPSTASH_REDIS_REST_TOKEN` | `YOUR_UPSTASH_REST_TOKEN` | **Same as Streamlit** |
| `SECRET_KEY` | `YOUR_43_CHAR_SECRET_KEY_HERE` | **Same as Streamlit** |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_EXPIRATION_HOURS` | `24` | |
| `ENCRYPTION_KEY` | `YOUR_44_CHAR_BASE64_ENCRYPTION_KEY_HERE` | **Same as Streamlit** |
| `API_KEY_PREFIX` | `gai_` | |
| `CORS_ORIGINS` | `https://geneai-research.streamlit.app,https://*.streamlit.app,http://localhost:8501,http://localhost:8502` | Update with your actual Streamlit URL |
| `NCBI_API_KEY` | *(optional)* | For enhanced PubMed access |
| `UNIPROT_API_KEY` | *(optional)* | For protein data |
| `OPENTARGETS_API_KEY` | *(optional)* | For target identification |
| `ALPHAFOLD_API_KEY` | *(optional)* | For structure prediction |
| `MODEL_DIR` | `data/models` | |
| `DEFAULT_MODEL` | `best_mutation_model_real.pkl` | |
| `ENABLE_SHAP` | `true` | |
| `ENABLE_MUTATION_ML` | `true` | |
| `ENABLE_REST_API` | `true` | |

---

## 🔒 Security Checklist (Before Deploy)

- [ ] **Generate NEW secrets** (don't use examples above)
  ```bash
  python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
  python -c "import base64, secrets; print('ENCRYPTION_KEY=' + base64.b64encode(secrets.token_bytes(32)).decode())"
  ```

- [ ] **Use SAME secrets** in both Streamlit and Render
- [ ] **Never commit** `.streamlit/secrets.toml` or `.env` files
- [ ] **Verify `.gitignore`** excludes:
  - `.streamlit/secrets.toml`
  - `.streamlit/secrets.toml.local`
  - `.env`
  - `.env.*`
  - `*.sqlite3`
  - `data/`

- [ ] **Test locally first:**
  ```bash
  # Set env vars locally
  export SECRET_KEY="your-generated-key"
  export ENCRYPTION_KEY="your-generated-key"
  export DATABASE_URL="your-neon-url"
  export UPSTASH_REDIS_REST_URL="your-upstash-url"
  export UPSTASH_REDIS_REST_TOKEN="your-upstash-token"
  
  # Run validator
  python validate_deployment.py
  ```

- [ ] **Redis is optional** - app works without it (caching disabled)
- [ ] **External APIs are optional** - enhanced features only

---

## 🚀 Next Deployment Steps

### 1. Generate Production Secrets
```bash
cd C:\Users\rahul\Documents\GeneAI_Research
python verify_secrets.py
```
Copy the output values.

### 2. Create Neon Database
- Go to https://console.neon.tech
- Create project → Copy connection string
- Ensure `?sslmode=require` at end

### 3. Create Upstash Redis
- Go to https://console.upstash.com
- Create Redis database → Copy REST URL + Token

### 4. Push to GitHub
```bash
git add .
git commit -m "Production secrets config ready"
git push origin main
```

### 5. Deploy Streamlit Cloud
- https://share.streamlit.io → New app → GitHub repo
- Paste secrets TOML in Advanced Settings
- Deploy

### 6. Deploy Render
- https://dashboard.render.com → New Web Service
- Connect GitHub repo
- Build: `pip install -r requirements-api.txt`
- Start: `uvicorn api_server:app --host 0.0.0.0 --port $PORT --workers 1`
- Add all environment variables from table above

### 7. Connect & Verify
- Update Streamlit `api_base_url` with actual Render URL
- Test: `https://your-api.onrender.com/health`
- Verify Streamlit sidebar shows "Deployment Status"

---

## 📝 Files Ready for Deployment

| File | Purpose |
|------|---------|
| `.streamlit/secrets.toml.example` | Streamlit secrets template |
| `render.yaml` | Render service configuration |
| `api_server.py` | FastAPI entry point for Render |
| `requirements-api.txt` | Lightweight deps for Render Free tier |
| `geneai/deployment_config.py` | Unified config (dev + prod) |
| `validate_deployment.py` | Pre-deployment validator |
| `.gitignore` | Excludes all secrets |

---

## ⚠️ Critical Reminders

1. **NEVER** paste real secrets in this document or commit to Git
2. **ALWAYS** use the platform secret managers (Streamlit Secrets, Render Env Vars)
3. **ROTATE** secrets if accidentally exposed
4. **MONITOR** free tier limits (Render sleeps after 15min, Neon suspends after 5min)
5. **BACKUP** Neon database before major changes

---

**Status: ✅ Ready for deployment. Secrets verified. Configuration complete.**