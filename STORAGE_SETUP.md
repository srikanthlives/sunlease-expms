# Storage Configuration Guide

This application supports two storage backends for file attachments:
1. **Local Storage** (default, for development)
2. **Google Drive** (recommended for production)

## Local Storage Setup (Development)

### Configuration

Files are stored in the `/data/uploads/` directory by default.

**Environment Variables:**
```bash
EXPMS_STORAGE_TYPE=local
EXPMS_UPLOAD_DIR=../data/uploads
EXPMS_MAX_UPLOAD_SIZE_MB=15
```

**No additional setup needed** - just create a `.env` file:
```bash
cp .env.example .env
```

The `/data` directory and `uploads` folder are automatically created when the app starts.

### File Organization

Uploads are organized by project folder, year, month, and week:
```
data/
└── uploads/
    ├── PROJ-A/
    │   └── 2026/
    │       └── 08/
    │           ├── W33/
    │           │   ├── a1b2c3d4e5f6g7h8.pdf
    │           │   ├── b2c3d4e5f6g7h8i9.jpg
    │           │   └── ...
    │           └── W34/
    │               ├── c3d4e5f6g7h8i9j0.pdf
    │               └── ...
    └── PROJ-B/
        └── 2026/
            ├── 08/
            └── 09/
```

**Organization Logic:**
- **Project Folder**: Uses project code (e.g., "PROJ-A", "GEN")
- **Year**: Current year (e.g., 2026)
- **Month**: Zero-padded month (01-12)
- **Week**: ISO week number, formatted as W01-W53
- **Files**: UUID4 with original extension for uniqueness

### Running Locally

#### Option A: Direct Python

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt

cd ..
python -m app.seed  # One-time: seed database

cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

#### Option B: Docker Compose

```bash
# Build and run
docker-compose up -d

# One-time: seed database
docker-compose exec app python -m app.seed

# View logs
docker-compose logs -f app

# Stop
docker-compose down
```

Then access the app at:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Frontend** (separate): http://localhost:5173

---

## Google Drive Setup (Production)

Google Drive storage is ideal for production because it's:
- **Free tier available**: 15GB free storage per Google account
- **Scalable**: No storage limits (beyond Google Drive account limits)
- **Easy to manage**: Files visible in Google Drive interface
- **Secure**: Access controlled by service account + folder sharing
- **Reliable**: Google's infrastructure

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click project dropdown → **New Project**
3. Name: `EXPMS` (or your choice)
4. Click **Create**
5. Wait for project to be created

### Step 2: Enable Google Drive API

1. In Google Cloud Console, search for **"Google Drive API"**
2. Click on it
3. Click **Enable**
4. Wait for it to be enabled

### Step 3: Create a Service Account

1. In Google Cloud Console, go to **IAM & Admin** → **Service Accounts**
2. Click **Create Service Account**
3. Fill in:
   - Service account name: `expms-app`
   - Service account ID: `expms-app` (auto-filled)
   - Description: `Service account for EXPMS file storage`
4. Click **Create and Continue**
5. Skip the optional step (click **Continue**)
6. Skip the third step (click **Done**)

### Step 4: Create and Download JSON Key

1. In Service Accounts, click on the newly created `expms-app` account
2. Go to **Keys** tab
3. Click **Add Key** → **Create new key**
4. Choose **JSON** format
5. Click **Create**
6. A JSON file (`expms-app-*.json`) will download automatically
7. Rename it to `gdrive-credentials.json` and keep it safe

### Step 5: Create Google Drive Folder

1. Go to [Google Drive](https://drive.google.com)
2. Click **New** → **Folder**
3. Name it: `expms-attachments`
4. Click **Create**

### Step 6: Share Folder with Service Account

1. Open the `expms-attachments` folder
2. Click **Share** (top right)
3. Copy the service account email from your JSON key file:
   - Open `gdrive-credentials.json` in a text editor
   - Find the field `"client_email"` (looks like: `expms-app@your-project.iam.gserviceaccount.com`)
4. Paste it into the Share dialog
5. Select **Editor** role
6. Uncheck "Notify people"
7. Click **Share**

### Step 7: Get Folder ID

1. Open the folder in Google Drive
2. Look at the URL in browser:
   ```
   https://drive.google.com/drive/folders/1ABC2DEF3GHI4JKL5MNO6PQR7STU8VWX
   ```
3. Copy the folder ID (the long alphanumeric part after `/folders/`)
4. Save this for later

### Step 8: Configure Application

**Option A: Local Development**

```bash
# Copy credentials file to project root
cp /path/to/gdrive-credentials.json ./

# Create .env file
cat > .env << EOF
EXPMS_STORAGE_TYPE=gdrive
EXPMS_GDRIVE_FOLDER_ID=<your-folder-id-from-step-7>
EXPMS_GDRIVE_CREDENTIALS_PATH=./gdrive-credentials.json
EOF

# Install dependencies
cd backend
pip install -r requirements.txt
cd ..

# Run
python -m app.seed
cd backend
uvicorn app.main:app --reload
```

**Option B: Docker Compose**

```bash
# Copy credentials
cp /path/to/gdrive-credentials.json ./

# Update docker-compose.yml:
# - Set EXPMS_STORAGE_TYPE=gdrive
# - Set EXPMS_GDRIVE_FOLDER_ID
# - Mount the credentials file

docker-compose up -d
docker-compose exec app python -m app.seed
```

**Option C: Railway Deployment**

See [RAILWAY_DEPLOYMENT.md](./RAILWAY_DEPLOYMENT.md) for detailed instructions.

### Step 9: Test Google Drive Connection

```bash
# Load .env and test
cd backend
source .venv/bin/activate
python -c "from app.services.storage import get_storage; s = get_storage(); print('✓ Google Drive connected successfully!')"
```

If it works, you'll see:
```
✓ Google Drive connected successfully!
```

If it fails, check:
1. Folder ID is correct
2. Credentials file exists and is valid
3. Service account has Editor access to the folder

### File Organization in Google Drive

Files are automatically organized in the shared folder by project, year, month, and week:
```
expms-attachments/
├── PROJ-A/
│   └── 2026/
│       └── 08/
│           ├── W33/
│           │   ├── a1b2c3d4e5f6g7h8.pdf
│           │   ├── b2c3d4e5f6g7h8i9.jpg
│           │   └── ...
│           └── W34/
│               ├── c3d4e5f6g7h8i9j0.pdf
│               └── ...
└── PROJ-B/
    └── 2026/
        ├── 08/
        └── 09/
```

**Organization Logic:**
- **Project Folder**: Uses project code (e.g., "PROJ-A", "GEN")
- **Year**: Current year (e.g., 2026)
- **Month**: Zero-padded month (01-12)
- **Week**: ISO week number, formatted as W01-W53
- **Files**: UUID4 with original extension for uniqueness

### Google Drive Advantages

- ✅ **Free tier**: 15GB free storage
- ✅ **Scalable**: Unlimited (within Google Drive limits)
- ✅ **Secure**: Folder-level access control
- ✅ **Visible**: Browse files in Google Drive interface
- ✅ **Shareable**: Can share with team members
- ✅ **Backed up**: Google maintains automatic backups
- ✅ **No setup**: Just a folder and service account

### Google Drive Costs

- **Storage**: Free (up to 15GB per account)
- **Beyond 15GB**: $1.99/month for 100GB, $9.99/month for 2TB
- **API calls**: Free (with quota limits, but very generous)

For a typical expense app, the free tier is usually sufficient.

---

## Switching Storage Backends

### From Local to Google Drive

1. Set up Google Drive (steps 1-8 above)
2. Update `.env`:
   ```
   EXPMS_STORAGE_TYPE=gdrive
   EXPMS_GDRIVE_FOLDER_ID=your-folder-id
   EXPMS_GDRIVE_CREDENTIALS_PATH=./gdrive-credentials.json
   ```
3. Restart app: `uvicorn app.main:app --reload`
4. **Note**: Existing files in `/data/uploads/` won't automatically migrate. Options:
   - Manually upload old files to Google Drive
   - Accept that old files are on local storage, new files go to Google Drive

### From Google Drive to Local

1. Update `.env`:
   ```
   EXPMS_STORAGE_TYPE=local
   EXPMS_UPLOAD_DIR=../data/uploads
   ```
2. Restart app
3. Same note about migration - existing Google Drive files won't auto-migrate to local

---

## Security Considerations

### Local Storage

- Files stored on server disk - subject to server security
- Access controlled via API endpoint authentication only (enforced)
- Backups must be managed manually
- Not suitable for distributed/scalable deployments

### Google Drive Storage

- Encrypted at rest (default)
- Access controlled by:
  - Google Drive folder permissions (folder-level)
  - Service account access (API level)
  - API endpoint authentication (enforced)
- Automatic backup (Google maintains)
- Suitable for all deployment scales
- Files are private by default (no public URLs unless shared)

### Best Practices

1. **Never commit credentials** - use `.env` files and `.gitignore`
2. **Rotate service account keys** every 90 days (download new key, upload to Railway, delete old key)
3. **Restrict folder access** - only the service account should have access
4. **Enable audit logging** - monitor who accesses the shared folder
5. **Limit file types** - upload restrictions already configured
6. **Restrict file size** - `EXPMS_MAX_UPLOAD_SIZE_MB` (default 15MB)

---

## Troubleshooting

### "File type not allowed"

Check `EXPMS_ALLOWED_UPLOAD_EXTENSIONS` in `.env`:
```bash
EXPMS_ALLOWED_UPLOAD_EXTENSIONS=.pdf,.jpg,.jpeg,.png,.webp,.xlsx,.csv
```

### "File exceeds max upload size"

Increase `EXPMS_MAX_UPLOAD_SIZE_MB`:
```bash
EXPMS_MAX_UPLOAD_SIZE_MB=50  # Allow up to 50MB
```

### Google Drive: "Permission denied"

1. Verify service account email is correct:
   ```bash
   cat gdrive-credentials.json | grep client_email
   ```
2. Verify folder is shared with that email address
3. Verify service account has **Editor** role (not Viewer)
4. Try re-sharing the folder

### Google Drive: "ImportError: No module named 'google'"

```bash
pip install google-auth-oauthlib google-api-python-client
```

### Google Drive: "Folder not found"

1. Verify folder ID:
   - Open folder in Google Drive
   - Copy from URL: `https://drive.google.com/drive/folders/FOLDER_ID`
2. Verify in `.env`: `EXPMS_GDRIVE_FOLDER_ID=<correct-id>`
3. Restart app

### Upload works but download fails

- **Local**: Check `/data/uploads/` directory exists and has correct permissions
- **Google Drive**: 
  - Verify service account still has access to folder
  - Try re-sharing the folder

### "rate limit exceeded"

Google Drive API has quota limits. If you hit them:
1. Wait a few minutes and retry
2. For production, contact Google Cloud to request quota increase
3. Usually not a problem for typical usage

---

## Docker Deployment

### Local Storage in Docker

```bash
docker-compose up -d
# Mounted volume: ./data:/app/data
```

### Google Drive in Docker

```bash
# Option 1: Mount credentials file
docker run -e EXPMS_STORAGE_TYPE=gdrive \
           -e EXPMS_GDRIVE_FOLDER_ID=your-folder-id \
           -v /path/to/gdrive-credentials.json:/app/gdrive-credentials.json \
           your-image

# Option 2: In docker-compose.yml
environment:
  EXPMS_STORAGE_TYPE: gdrive
  EXPMS_GDRIVE_FOLDER_ID: your-folder-id
  EXPMS_GDRIVE_CREDENTIALS_PATH: /app/gdrive-credentials.json
volumes:
  - ./gdrive-credentials.json:/app/gdrive-credentials.json:ro
```

---

## Migration from Old Storage

If you had a previous storage implementation:

### Migrate from Local to Google Drive

```bash
# 1. In Google Drive, create subfolders matching your structure
#    (app will auto-create these, but you can pre-create them)

# 2. Update .env to use Google Drive

# 3. New uploads will go to Google Drive
#    Old local files stay where they are but won't be accessible via app
```

### Update Database URLs

If old files had different paths, update the database:
```sql
-- Only if needed for old local files
UPDATE documents SET stored_filename = 
  CONCAT('2026/08/', SUBSTRING(stored_filename, -40))
WHERE storage_url LIKE '%.pdf';
```

---

## Production Checklist

- [ ] Google Drive folder created and shared with service account
- [ ] Service account has Editor access to folder
- [ ] Credentials JSON downloaded and stored securely
- [ ] Folder ID verified and in `.env`
- [ ] Test upload/download works
- [ ] Database backed up
- [ ] CORS origins restricted to your domain
- [ ] File upload extensions/MIME types restricted
- [ ] Max upload size set appropriately
- [ ] Monitoring/alerting configured
- [ ] Regular backups scheduled (if using SQLite)

---

## Useful Links

- [Google Drive API Docs](https://developers.google.com/drive)
- [Service Account Setup](https://cloud.google.com/iam/docs/service-accounts)
- [FastAPI Docs](https://fastapi.tiangolo.com)
- [Your App API Docs](http://localhost:8000/docs)
