# GeneAI Research - Free Deployment Guide

## 🎯 Overview

This guide covers deploying GeneAI Research to **completely free tiers**:

| Service | Platform | Free Tier Limits |
|---------|----------|------------------|
| **Frontend (Streamlit)** | Streamlit Community Cloud | Unlimited public apps, 1 GB RAM, 1 CPU |
| **Backend (FastAPI)** | Render Free | 750 hrs/month, 512 MB RAM, auto-sleeps after 15 min |
| **Database (PostgreSQL)** | Neon Free | 512 MB storage, 100 hrs compute/month, auto-suspend |
| **Cache (Redis)** | Upstash Free | 10,000 req/day, 256 MB storage, serverless |

**Total Monthly Cost: ₹0**

---

## 📋 Prerequisites

1. **GitHub Account** - For source code hosting
2. **Streamlit Community Cloud Account** - https://share.streamlit.io
3. **Render Account** - https://render.com
4. **Neon Account** - https://neon.tech
5. **Upstash Account** - https://upstash.com

All services offer generous free tiers without requiring credit cards.

---

## 🗄️ Step 1: Create Neon PostgreSQL Database

1. Go to https://console.neon.tech
2. Click **"Create Project"**
3. Configure:
   - **Name**: `geneai-research`
   - **PostgreSQL Version**: 15 (default)
   - **Region**: Choose closest to your users
4. Click **"Create Project"**
5. **Copy the connection string** (looks like):
   ```
   postgresql://user:password@ep-xxx.us-east-1.aws.neon.tech/geneai?sslmode=require
   ```
6. **Save this for later** - you'll need it for both Streamlit and Render

### Initialize Database Schema

The database schema is auto-created on first run, but you can pre-initialize:

```bash
# Optional: Run locally with Neon connection to create tables
DATABASE_URL="your-neon-connection-string" python -c "
from geneai.unified_knowledge.database import KnowledgeDatabase, DatabaseConfig
config = DatabaseConfig(db_path='your-neon-connection-string')
db = KnowledgeDatabase(config)
print('Database initialized successfully')
"
```

---

## 🔴 Step 2: Create Upstash Redis Database

1. Go to https://console.upstash.com
2. Click **"Create Database"**
3. Configure:
   - **Name**: `geneai-research`
   - **Type**: **Redis** (not Kafka)
   - **Region**: Choose closest to Render (Oregon/us-east-1 recommended)
   - **TLS**: Enabled (required)
4. Click **"Create"**
5. **Copy these values**:
   - **REST URL**: `https://xxx.upstash.io`
   - **REST Token**: `your-token-here`
6. **Save for later**

---

## 🎨 Step 3: Deploy to Streamlit Community Cloud

### 3.1 Prepare Repository

1. Push your code to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit for free deployment"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/geneai-research.git
   git push -u origin main
   ```

### 3.2 Deploy on Streamlit Cloud

1. Go to https://share.streamlit.io
2. Click **"New app"**
3. Connect your GitHub repository:
   - **Repository**: `YOUR_USERNAME/geneai-research`
   - **Branch**: `main`
   - **Main file path**: `app.py`
4. Click **"Advanced settings"**
5. **Add Secrets** (copy from `.streamlit/secrets.toml.example` and fill in):

```toml
[database]
url = "postgresql://user:password@ep-xxx.us-east-1.aws.neon.tech/geneai?sslmode=require"

[redis]
url = "https://xxx.upstash.io"
token = "your-upstash-token"

[security]
secret_key = "your-32-char-secret-key-here"
encryption_key = "your-base64-encoded-32-byte-key"

[app]
api_base_url = "https://geneai-api.onrender.com"

[external_apis]
ncbi_api_key = ""
uniprot_api_key = ""
opentargets_api_key = ""
alphafold_api_key = ""

[features]
enable_multi_user = true
enable_rest_api = true
enable_mutation_ml = true
```

**Generate secrets locally:**
```bash
# Secret key (32+ chars)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Encryption key (base64 encoded 32 bytes)
python -c "import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

6. Click **"Deploy!"**

### 3.3 Verify Streamlit Deployment

- Wait for build to complete (2-5 minutes)
- Your app will be at: `https://geneai-research.streamlit.app`
- Check the sidebar for "Deployment Status" showing configuration

---

## ⚡ Step 4: Deploy FastAPI to Render

### 4.1 Create Render Service

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository: `YOUR_USERNAME/geneai-research`
4. Configure:
   - **Name**: `geneai-api`
   - **Region**: Oregon (US West) or Frankfurt (EU) or Singapore
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install --upgrade pip && pip install -r requirements-api.txt`
   - **Start Command**: `uvicorn api_server:app --host 0.0.0.0 --port $PORT --workers 1`
   - **Plan**: **Free**

### 4.2 Add Environment Variables

In Render dashboard → **Environment** tab, add:

| Key | Value | Notes |
|-----|-------|-------|
| `DATABASE_URL` | Your Neon connection string | From Step 1 |
| `UPSTASH_REDIS_REST_URL` | Your Upstash REST URL | From Step 2 |
| `UPSTASH_REDIS_REST_TOKEN` | Your Upstash REST Token | From Step 2 |
| `SECRET_KEY` | Generated 32+ char secret | Same as Streamlit |
| `ENCRYPTION_KEY` | Base64 encoded 32-byte key | Same as Streamlit |
| `CORS_ORIGINS` | `https://geneai-research.streamlit.app,https://*.streamlit.app` | Your Streamlit URL |
| `API_BASE_URL` | `https://geneai-api.onrender.com` | Your Render URL (after deploy) |
| `ENABLE_MUTATION_ML` | `true` | Enable ML features |
| `ENABLE_REST_API` | `true` | Enable REST API |

**Optional (for enhanced features):**
| Key | Value |
|-----|-------|
| `NCBI_API_KEY` | Your NCBI key |
| `UNIPROT_API_KEY` | Your UniProt key |
| `OPENTARGETS_API_KEY` | Your OpenTargets key |
| `ALPHAFOLD_API_KEY` | Your AlphaFold key |

### 4.3 Deploy and Verify

1. Click **"Create Web Service"**
2. Wait for build (3-5 minutes)
3. Your API will be at: `https://geneai-api.onrender.com`
4. Test endpoints:
   - Health: `https://geneai-api.onrender.com/health`
   - Ready: `https://geneai-api.onrender.com/ready`
   - Models: `https://geneai-api.onrender.com/models`

---

## 🔗 Step 5: Connect Streamlit to Render API

1. In Streamlit Cloud dashboard → **Settings** → **Secrets**
2. Update `api_base_url`:
   ```toml
   [app]
   api_base_url = "https://geneai-api.onrender.com"
   ```
3. Click **"Save"** → App will auto-redeploy
4. Verify in Streamlit sidebar "Deployment Status" shows correct API URL

---

## ✅ Step 6: Validate Full Deployment

### Test Checklist

- [ ] Streamlit app loads at `https://geneai-research.streamlit.app`
- [ ] Sidebar shows "Deployment Status" with all green checks
- [ ] FastAPI health check returns 200: `https://geneai-api.onrender.com/health`
- [ ] ML models listed: `https://geneai-api.onrender.com/models`
- [ ] Database connected (check logs for "PostgreSQL database configured")
- [ ] Redis connected (check logs for "Upstash Redis configured")
- [ ] Test mutation prediction in ML Dashboard
- [ ] Test multi-user features (login/register)
- [ ] Test REST API endpoints from Streamlit

### Common Issues

| Issue | Solution |
|-------|----------|
| Render service sleeps | Free tier sleeps after 15 min inactivity. First request takes 30-60s to wake up. |
| Neon compute suspended | Neon auto-suspends after 5 min. First query takes 1-2s to resume. |
| CORS errors | Ensure `CORS_ORIGINS` in Render matches your exact Streamlit URL |
| Model not loading | Check `data/models/` exists in repo or download on startup |
| Memory limit exceeded | Remove heavy ML deps (xgboost, lightgbm, shap) from `requirements-api.txt` |

---

## 🔧 Step 7: Custom Domain (Optional)

### Streamlit Custom Domain
1. Streamlit Cloud → Settings → Custom Domains
2. Add your domain (e.g., `app.yourdomain.com`)
3. Configure DNS CNAME to `geneai-research.streamlit.app`

### Render Custom Domain
1. Render Dashboard → Settings → Custom Domains
2. Add your domain (e.g., `api.yourdomain.com`)
3. Configure DNS CNAME to `geneai-api.onrender.com`
4. Update `CORS_ORIGINS` and `api_base_url` to use custom domains

---

## 💰 Cost Summary

| Service | Free Tier | Your Usage | Cost |
|---------|-----------|------------|------|
| Streamlit Cloud | Unlimited public apps | 1 app | **₹0** |
| Render Free | 750 hrs/month | ~720 hrs (24/7) | **₹0** |
| Neon Free | 512 MB storage | ~50 MB | **₹0** |
| Upstash Free | 10k req/day | ~1k req/day | **₹0** |
| **Total** | | | **₹0/month** |

---

## 🔄 CI/CD Pipeline

The included `.github/workflows/ci-cd.yml` runs on every push:
- ✅ Linting (Ruff)
- ✅ Type Checking (MyPy)
- ✅ Unit Tests
- ✅ Security Scan (Bandit + Safety)
- ✅ Docker Build
- ✅ Deploy to Staging/Production (manual approval)

For free deployment, you can disable the Docker build step since you're using Render + Streamlit Cloud directly.

---

## 📝 Maintenance

### Weekly
- Check Render service is running (auto-sleeps after 15 min inactivity)
- Monitor Neon storage usage
- Check Upstash request quota

### Monthly
- Rotate secrets (SECRET_KEY, ENCRYPTION_KEY)
- Update dependencies: `pip install -U -r requirements.txt`
- Review logs for errors

### Model Updates
To deploy new ML models:
1. Train locally
2. Commit `data/models/new_model.pkl` to GitHub
3. Update `DEFAULT_MODEL` in Render environment variables
4. Render auto-deploys on push

---

## 🆘 Troubleshooting

### Streamlit Build Fails
```bash
# Check logs in Streamlit dashboard
# Common fix: Ensure all imports work
python -c "import geneai; print('OK')"
```

### Render Build Fails
```bash
# Check Render build logs
# Common fix: Memory limit - remove heavy deps from requirements-api.txt
```

### Database Connection Fails
```bash
# Verify Neon connection string format
# Must include: ?sslmode=require
# Test locally: psql "your-connection-string"
```

### Redis Connection Fails
```bash
# Verify Upstash REST URL and Token
# Test: curl -H "Authorization: Bearer YOUR_TOKEN" https://xxx.upstash.io/ping
```

---

## 📚 Additional Resources

- **Streamlit Cloud Docs**: https://docs.streamlit.io/streamlit-community-cloud
- **Render Free Tier**: https://render.com/docs/free
- **Neon Free Tier**: https://neon.tech/docs/introduction/free-tier
- **Upstash Free Tier**: https://upstash.com/docs/redis/free-tier

---

## 🎉 You're Live!

Your GeneAI Research platform is now deployed for **FREE** at:
- **Frontend**: https://geneai-research.streamlit.app
- **API**: https://geneai-api.onrender.com

All Phases 1-7 features are preserved and running on free infrastructure!