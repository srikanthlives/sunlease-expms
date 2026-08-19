# Railway Deployment Guide

This guide explains how to deploy the Expense & Payment Management System to Railway.app with Google Drive for storing attachments.

## Prerequisites

1. **Railway Account**: Create an account at [railway.app](https://railway.app)
2. **GitHub Repository**: Push your code to GitHub (Railway integrates with GitHub)
3. **Google Drive Account**: For storing attachments (recommended for free/cost-effective storage)
4. **Domain** (optional): Custom domain for your app

## Step 1: Prepare Your Repository

Ensure your repository structure includes:
```
.
├── Dockerfile          # Already created
├── docker-compose.yml  # For local testing
├── .env.example        # Template for environment variables
├── frontend/           # React app
└── backend/            # FastAPI app
```

Commit all changes to GitHub:
```bash
git add .
git commit -m "Add Docker and Railway deployment configuration"
git push origin main
```

## Step 2: Set Up Google Drive Storage (Recommended)

### 2a. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Google Drive API**:
   - Search for "Google Drive API"
   - Click **Enable**

### 2b. Create a Service Account

1. Go to **IAM & Admin** → **Service Accounts**
2. Click **Create Service Account**
3. Fill in details:
   - Service account name: `expms-app`
   - Click **Create and Continue**
4. Skip adding members - click **Continue**
5. Create a JSON key:
   - Click on the created service account
   - Go to **Keys** tab
   - Click **Add Key** → **Create new key** → **JSON**
   - Download and save the JSON file locally (keep it secret!)

### 2c. Create Google Drive Folder for Uploads

1. Go to [Google Drive](https://drive.google.com)
2. Create a new folder: `expms-attachments`
3. Right-click the folder → **Share**
4. Add the service account email: `expms-app@sunlease-expms.iam.gserviceaccount.com`
5. Grant **Editor** access
6. Click **Share**

### 2d. Get the Folder ID

1. Open the folder in Google Drive
2. Look at the URL: `https://drive.google.com/drive/folders/FOLDER_ID` - https://drive.google.com/drive/u/1/folders/1vezMDBKNXMN76knihgGzRtMv9H9rw1z6
3. Copy the `FOLDER_ID` (long alphanumeric string)

## Step 3: Deploy to Railway

### 3a. Connect GitHub Repository

1. Go to [railway.app](https://railway.app) and log in
2. Click **New Project**
3. Select **Deploy from GitHub repo**
4. Authorize Railway to access your GitHub account
5. Select your repository
6. Railway will automatically detect the `Dockerfile` and create a deployment

### 3b. Configure Environment Variables

1. Once the project is created, click on it
2. Go to the **Variables** section
3. Add the following environment variables:

**Essential Settings:**
```
EXPMS_SECRET_KEY=<generate-a-strong-random-key>
EXPMS_DATABASE_URL=sqlite:////app/data/expms.db
EXPMS_CORS_ORIGINS=https://your-domain.com,https://www.your-domain.com
```

**For Google Drive Storage (Recommended):**
```
EXPMS_STORAGE_TYPE=gdrive
EXPMS_GDRIVE_FOLDER_ID=1vezMDBKNXMN76knihgGzRtMv9H9rw1z6
EXPMS_GDRIVE_CREDENTIALS_PATH=/app/gdrive-credentials.json
```

**File Upload Settings:**
```
EXPMS_MAX_UPLOAD_SIZE_MB=15
EXPMS_ALLOWED_UPLOAD_EXTENSIONS=.pdf,.jpg,.jpeg,.png,.webp,.xlsx,.csv
EXPMS_ALLOWED_UPLOAD_MIME_TYPES=application/pdf,image/jpeg,image/png,image/webp,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv
```

### 3c. Add Google Drive Credentials

You have two options:

**Option A: Pass credentials as environment variable (Recommended for Railway)**

1. Open the JSON key file you downloaded (`gdrive-credentials.json`) with a text editor
2. Copy the entire JSON content
3. In Railway Variables, create: `GDRIVE_CREDENTIALS_JSON` with the entire JSON as value
4. Update your Dockerfile or create a startup script to save it:

Create a file `backend/setup-gdrive-creds.sh`:
```bash
#!/bin/bash
if [ -n "$GDRIVE_CREDENTIALS_JSON" ]; then
  echo "$GDRIVE_CREDENTIALS_JSON" > /app/gdrive-credentials.json
fi
exec "$@"
```

Update `Dockerfile`:
```dockerfile
# ... existing content ...
COPY backend/setup-gdrive-creds.sh /app/
RUN chmod +x /app/setup-gdrive-creds.sh

ENTRYPOINT ["/app/setup-gdrive-creds.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Option B: Mount credentials file**

1. In Railway, go to **Volumes**
2. Add a volume mount for the credentials file
3. Upload the `gdrive-credentials.json` file

## Step 4: Configure Database

### Option A: SQLite (Quick Testing)

Default setup uses SQLite stored in `/app/data/expms.db`. Railway provides persistent volume storage.

**Request persistent volume in Railway:**
1. Go to **Volumes** section
2. Add a volume: mount it to `/app/data`
3. This ensures your database persists across deployments

### Option B: PostgreSQL (Recommended for Production)

1. In Railway project, click **Create** → **Add Service**
2. Select **PostgreSQL**
3. Railway automatically creates a database
4. Get connection string from PostgreSQL service variables
5. Set `EXPMS_DATABASE_URL`:
```
EXPMS_DATABASE_URL=postgresql://user:password@postgres-host:5432/railway
```

## Step 5: Deploy and Test

1. Railway automatically deploys when you push to GitHub
2. Watch the deployment logs in Railway dashboard
3. Once deployment is successful, Railway provides a public URL

**First Run Setup:**
1. The backend will auto-run migrations on startup
2. Seed the database (one-time):

```bash
# Via Railway terminal or SSH
cd /app
python -m app.seed
```

## Step 6: Set Up Custom Domain (Optional)

1. In Railway project, go to **Settings** → **Domain**
2. Click **Add Custom Domain**
3. Enter your domain (e.g., `expms.yourdomain.com`)
4. Update DNS records in your domain provider:
   - Add CNAME record pointing to Railway's provided URL
5. Railway auto-provisions SSL certificate

## Environment Variables Reference

| Variable | Example | Description |
|----------|---------|-------------|
| `EXPMS_SECRET_KEY` | `random-secret-key` | JWT secret key (generate via `openssl rand -hex 32`) |
| `EXPMS_DATABASE_URL` | `sqlite:////app/data/expms.db` or `postgresql://...` | Database connection string |
| `EXPMS_STORAGE_TYPE` | `gdrive` or `local` | Storage backend |
| `EXPMS_GDRIVE_FOLDER_ID` | `1ABC2DEF3GHI...` | Google Drive folder ID for uploads |
| `EXPMS_GDRIVE_CREDENTIALS_PATH` | `/app/gdrive-credentials.json` | Path to credentials file |
| `GDRIVE_CREDENTIALS_JSON` | `{full JSON content}` | Full credentials JSON (alternative to file) |
| `EXPMS_CORS_ORIGINS` | `https://yourdomain.com` | Allowed frontend origins (comma-separated) |
| `EXPMS_MAX_UPLOAD_SIZE_MB` | `15` | Max file upload size in MB |

## Troubleshooting

### Deployment Fails

Check Railway logs:
1. Go to **Deployments** tab
2. Click on failed deployment
3. Review **Build Logs** and **Deploy Logs**

Common issues:
- Missing `Dockerfile`: Ensure it's in repo root
- Python dependency error: Check `requirements.txt` syntax
- Port not exposed: Dockerfile runs on port 8000 (correct)

### Database Issues

- **SQLite database not persisting**: Ensure the volume is mounted at `/app/data`
- **PostgreSQL connection fails**: Verify `EXPMS_DATABASE_URL` is correct and PostgreSQL service is running

### Google Drive Upload Fails

```
FileNotFoundError: gdrive-credentials.json not found
```
Solution: Ensure credentials are passed via `GDRIVE_CREDENTIALS_JSON` env var or file is mounted

```
PermissionError: Service account doesn't have access to folder
```
Solution: 
1. Verify folder ID is correct
2. Ensure service account email has Editor access to the shared folder
3. Try sharing the folder again with the exact service account email

### Attachment Download Fails

- Check `EXPMS_STORAGE_TYPE` is set to `gdrive`
- Verify folder ID is correct in `EXPMS_GDRIVE_FOLDER_ID`
- Ensure service account has read access to the folder
- Check credentials JSON is valid and not corrupted

## Monitoring

### Health Check

Railway automatically monitors:
```
GET http://your-app/api/v1/health
```

The Dockerfile includes a health check definition.

### Logs

View real-time logs in Railway dashboard under **Logs** tab.

### Database Backup

For PostgreSQL:
1. Use Railway's built-in backup feature
2. Or use `pg_dump` manually

For SQLite:
1. Download the `expms.db` file from mounted volume
2. Keep regular backups

## Security Best Practices

1. **Rotate Secrets**: Change `EXPMS_SECRET_KEY` in production
2. **Use HTTPS Only**: Railway provides automatic SSL
3. **Restrict CORS**: Set `EXPMS_CORS_ORIGINS` to your frontend domain only
4. **Secure Google Drive Credentials**: Never commit credentials to Git, use environment variables
5. **Database Access**: Don't expose database directly, access via API only
6. **Regular Updates**: Keep dependencies updated (`pip list --outdated`)

## Local Development with Docker

Test locally before deploying:

```bash
# Build and run with docker-compose
docker-compose up -d

# Seed database
docker-compose exec app python -m app.seed

# View logs
docker-compose logs -f app

# Stop
docker-compose down
```

## Rollback to Previous Version

In Railway:
1. Go to **Deployments** tab
2. Click on a previous successful deployment
3. Click **Redeploy**

## Getting Help

- **Railway Docs**: https://docs.railway.app
- **FastAPI Docs**: https://fastapi.tiangolo.com
- **Google Drive API**: https://developers.google.com/drive
- **Your App API Docs**: `https://your-app/docs` (Swagger UI)
