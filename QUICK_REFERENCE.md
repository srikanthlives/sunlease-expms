# Configuration & Storage Quick Reference

## Quick Start

### 1. Local Development (Default)

```bash
# Copy environment template
cp .env.example .env

# Install dependencies
cd backend
pip install -r requirements.txt
cd ..

# Run directly
python -m app.seed
cd backend
uvicorn app.main:app --reload

# Or with Docker
docker-compose up -d
docker-compose exec app python -m app.seed
```

**Access:**
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

### 2. Production with Google Drive

```bash
# Download Google Drive service account JSON from Google Cloud Console
# Place it as: ./gdrive-credentials.json

# Update .env
cat > .env << EOF
EXPMS_SECRET_KEY=$(openssl rand -hex 32)
EXPMS_DATABASE_URL=postgresql://user:pass@host/dbname
EXPMS_STORAGE_TYPE=gdrive
EXPMS_GDRIVE_FOLDER_ID=your-folder-id-here
EXPMS_GDRIVE_CREDENTIALS_PATH=./gdrive-credentials.json
EXPMS_CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
EOF

# Run
docker-compose up -d
```

---

### 3. Railway Deployment

```bash
# 1. Push to GitHub
git add .
git commit -m "Ready for Railway"
git push origin main

# 2. Go to railway.app and create new project from GitHub repo

# 3. Set these environment variables in Railway dashboard:
EXPMS_SECRET_KEY=<generate-strong-key>
EXPMS_DATABASE_URL=postgresql://user:pass@postgres/railway
EXPMS_STORAGE_TYPE=gdrive
EXPMS_GDRIVE_FOLDER_ID=your-folder-id
EXPMS_GDRIVE_CREDENTIALS_PATH=/app/gdrive-credentials.json
EXPMS_CORS_ORIGINS=https://your-railway-domain

# 4. Add /data volume to persist database
# (In Railway: Volumes → Add → Mount: /data)

# 5. Railway auto-deploys from git
```

---

## Environment Variables

| Variable | Default | Example |
|----------|---------|---------|
| `EXPMS_SECRET_KEY` | dev-secret | `$(openssl rand -hex 32)` |
| `EXPMS_DATABASE_URL` | sqlite:///expms.db | `postgresql://user:pass@localhost/db` |
| `EXPMS_STORAGE_TYPE` | local | `local` or `gdrive` |
| `EXPMS_UPLOAD_DIR` | ../data/uploads | `/var/uploads` |
| `EXPMS_GDRIVE_FOLDER_ID` | (empty) | `1ABC2DEF3GHI4JKL5MNO6PQR` |
| `EXPMS_GDRIVE_CREDENTIALS_PATH` | ./gdrive-credentials.json | `/app/credentials.json` |
| `EXPMS_MAX_UPLOAD_SIZE_MB` | 15 | `50` |
| `EXPMS_CORS_ORIGINS` | localhost:5173 | `https://app.mysite.com` |

---

## Storage Comparison

| Feature | Local | Google Drive |
|---------|-------|-----|
| Setup Complexity | ⭐ Easy | ⭐⭐ Medium |
| Cost | Free | Free (15GB) |
| Scalability | Limited | Unlimited |
| Backup | Manual | Automatic |
| Best For | Development | Production |

---

## Common Commands

```bash
# Seed database (one-time)
python -m app.seed

# Database migration (automatic)
python -m app.migrate

# Run tests
cd backend
pytest

# Docker: Build image
docker build -t expms:latest .

# Docker: Run
docker run -p 8000:8000 \
  -e EXPMS_STORAGE_TYPE=local \
  -v $(pwd)/data:/app/data \
  expms:latest

# Docker Compose: Start
docker-compose up -d

# Docker Compose: Logs
docker-compose logs -f app

# Docker Compose: Stop
docker-compose down
```

---

## File Paths

**Local Storage Organization:**
```
project-root/
└── data/
    ├── expms.db (SQLite database)
    └── uploads/
        ├── PROJ-A/2026/08/W33/ (organized by project/year/month/week)
        ├── PROJ-B/2026/08/W34/
        └── default/2026/08/W33/ (if no project specified)
```

**Google Drive Organization:**
```
Google Drive > expms-attachments/
├── PROJ-A/2026/08/W33/ (organized by project/year/month/week)
├── PROJ-B/2026/08/W34/
└── default/2026/08/W33/ (if no project specified)
```

Files within each folder are named with UUID4 + extension (e.g., `a1b2c3d4e5f6g7h8.pdf`)

---

## Testing Storage Locally

### Test Local Storage
```bash
# Create test file
echo "test" > test.txt

# Upload via API
curl -X POST "http://localhost:8000/api/v1/documents" \
  -H "Authorization: Bearer your-token" \
  -F "file=@test.txt" \
  -F "document_type=EXPENSE" \
  -F "expense_id=1"

# File should appear in data/uploads/2026/08/
ls -la data/uploads/2026/08/
```

### Test Google Drive Storage
```bash
# Verify connection
cd backend
python -c "from app.services.storage import get_storage; print(get_storage())"
# Output: GoogleDriveStorageBackend() means it worked!

# Upload should now go to Google Drive folder
# Verify in Google Drive web interface
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `FileNotFoundError: gdrive-credentials.json` | Place GCS key in project root, or set `EXPMS_GDRIVE_CREDENTIALS_PATH` |
| `ImportError: google.auth` | Run `pip install google-auth-oauthlib google-api-python-client` |
| `PermissionError: /data/uploads` | Ensure `/data` volume is mounted in Docker |
| `ModuleNotFoundError: app` | Run from project root, not from `backend/` |
| `CORS error in frontend` | Update `EXPMS_CORS_ORIGINS` to match frontend URL |
| `Google Drive folder not found` | Verify folder ID and service account access |

---

## Deployment Checklist

- [ ] `.env` file created and added to `.gitignore`
- [ ] Database migrations run (`python -m app.migrate`)
- [ ] Test data seeded (`python -m app.seed`)
- [ ] File upload tested (local or Google Drive)
- [ ] API health check passes (`/api/v1/health`)
- [ ] Frontend builds without errors (`npm run build`)
- [ ] Docker image builds successfully
- [ ] Environment variables set in production
- [ ] Database backup configured
- [ ] CORS origins restricted to your domain
- [ ] SSL certificate configured
- [ ] Monitoring/logging enabled

---

## Documentation Files

- **`RAILWAY_DEPLOYMENT.md`** - Complete Railway deployment guide
- **`STORAGE_SETUP.md`** - Detailed storage backend configuration
- **`README.md`** - General project information
- **`.env.example`** - Environment variable template

---

## Support

- API Docs: http://localhost:8000/docs
- FastAPI: https://fastapi.tiangolo.com
- Google Drive API: https://developers.google.com/drive
- Railway: https://railway.app
