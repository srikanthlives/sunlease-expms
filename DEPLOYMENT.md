# Deployment Guide

Covers Docker, storage backends, and Railway deployment. For local dev
without Docker, see [README.md](./README.md).

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `EXPMS_SECRET_KEY` | *(none — required)* | JWT signing key. Generate with `openssl rand -hex 32`. Never commit a real value. |
| `EXPMS_DATABASE_URL` | `sqlite:///../data/expms.db` | Or `postgresql://user:pass@host/dbname` |
| `EXPMS_STORAGE_TYPE` | `local` | `local` or `gdrive` |
| `EXPMS_UPLOAD_DIR` | `../data/uploads` | Used when `EXPMS_STORAGE_TYPE=local` |
| `EXPMS_GDRIVE_FOLDER_ID` | *(empty)* | Used when `EXPMS_STORAGE_TYPE=gdrive` |
| `EXPMS_GDRIVE_CREDENTIALS_PATH` | `./gdrive-credentials.json` | Path to the service-account JSON key |
| `EXPMS_MAX_UPLOAD_SIZE_MB` | `15` | |
| `EXPMS_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |

Copy `.env.example` to `.env` and fill in real values. `.env` and
`gdrive-credentials.json` are gitignored — never commit either.

## Docker

The `Dockerfile` is a multi-stage build: it builds the frontend, then copies
the built assets and backend into a slim Python image. Both the container
and bare-metal dev use the same entrypoint, `startup.sh`, which detects
whether it's running inside Docker and skips the venv/npm-install steps
there since the image already has everything baked in.

```bash
# Build and run
docker-compose up -d

# One-time: seed the database
docker-compose exec app python -m app.seed

# Logs / stop
docker-compose logs -f app
docker-compose down
```

`docker-compose.yml` requires `EXPMS_SECRET_KEY` to be set (via `.env` or
your shell environment) — it will refuse to start otherwise.

Access: API at `http://localhost:8000`, docs at `http://localhost:8000/docs`.

### Running the image directly (no compose)

```bash
docker build -t expms:latest .
docker run -p 8000:8000 \
  -e EXPMS_SECRET_KEY=$(openssl rand -hex 32) \
  -e EXPMS_STORAGE_TYPE=local \
  -v $(pwd)/data:/app/data \
  expms:latest
```

## Storage backends

Files are organized as `<project-code>/<year>/<month>/W<week>/<uuid4>.<ext>`
under either the local upload dir or the Google Drive folder — same layout
either way.

### Local (default, good for dev / single-server deployments)

```
EXPMS_STORAGE_TYPE=local
EXPMS_UPLOAD_DIR=../data/uploads
```

No further setup — the directory is created automatically on first run.

### Google Drive (good when you want offsite backup without running Postgres/S3)

1. In [Google Cloud Console](https://console.cloud.google.com/), create/select
   a project and enable the **Google Drive API**.
2. **IAM & Admin → Service Accounts → Create Service Account.** Add a JSON
   key (**Keys → Add Key → Create new key → JSON**) and download it.
3. In [Google Drive](https://drive.google.com), create a folder for
   attachments. Share it with the service account's `client_email` (from
   the JSON key) as **Editor**.
4. Copy the folder ID from the folder's URL
   (`.../drive/folders/<FOLDER_ID>`).
5. Set:
   ```
   EXPMS_STORAGE_TYPE=gdrive
   EXPMS_GDRIVE_FOLDER_ID=<folder-id-from-step-4>
   EXPMS_GDRIVE_CREDENTIALS_PATH=./gdrive-credentials.json
   ```
   (place the downloaded key at that path — it's gitignored).
6. Verify: `python -c "from app.services.storage import get_storage; get_storage()"`
   from `backend/` — no exception means it connected.

Switching backends does **not** migrate existing files — old files stay
wherever they were written; only new uploads follow the new setting.

Google Drive free tier is 15GB; beyond that it's Google's standard Drive
storage pricing.

## Railway deployment

1. Push the repo to GitHub. Railway auto-detects the `Dockerfile`.
2. **New Project → Deploy from GitHub repo**, select this repo.
3. **Variables** — set at minimum:
   ```
   EXPMS_SECRET_KEY=<openssl rand -hex 32>
   EXPMS_DATABASE_URL=sqlite:////app/data/expms.db
   EXPMS_CORS_ORIGINS=https://your-railway-domain
   ```
   For Google Drive storage, also set `EXPMS_STORAGE_TYPE=gdrive`,
   `EXPMS_GDRIVE_FOLDER_ID`, and `EXPMS_GDRIVE_CREDENTIALS_PATH=/app/gdrive-credentials.json`.
4. **Credentials for Google Drive on Railway** (no persistent file upload
   in the dashboard, so pass the JSON as an env var instead): set
   `GDRIVE_CREDENTIALS_JSON` to the full contents of the service-account
   JSON key. `startup.sh` writes it to `EXPMS_GDRIVE_CREDENTIALS_PATH` on
   container start automatically — no Dockerfile changes needed.
5. **Volumes** — add a volume mounted at `/app/data` so the SQLite database
   (and local uploads, if using `EXPMS_STORAGE_TYPE=local`) survive
   redeploys. For production-grade Postgres instead, add Railway's
   PostgreSQL plugin and point `EXPMS_DATABASE_URL` at it.
6. Push to `main` — Railway redeploys automatically. First deploy: run
   `python -m app.seed` once via the Railway terminal to create the initial
   users.
7. Optional: **Settings → Domain → Add Custom Domain**, then add the CNAME
   Railway gives you at your DNS provider. SSL is automatic.

### Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails at build | Check `Dockerfile` is at repo root and `backend/requirements.txt` is valid |
| SQLite resets on every deploy | Volume isn't mounted at `/app/data` |
| `FileNotFoundError: gdrive-credentials.json` | `GDRIVE_CREDENTIALS_JSON` env var not set, or path mismatch |
| `PermissionError` from Google Drive | Folder not shared with the service account's `client_email`, or shared as Viewer instead of Editor |
| CORS errors in the browser | `EXPMS_CORS_ORIGINS` doesn't include the frontend's actual origin |

### Health check

Both the Dockerfile and Railway hit `GET /api/v1/health` to determine
container health.
