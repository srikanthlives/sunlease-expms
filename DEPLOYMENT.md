# Deployment Guide

Covers Docker, storage backends, and Railway deployment. For local dev
without Docker, see [README.md](./README.md).

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `EXPMS_SECRET_KEY` | *(none — required)* | JWT signing key. Generate with `openssl rand -hex 32`. Never commit a real value. |
| `EXPMS_DATABASE_URL` | `sqlite:///../data/expms.db` | Or `postgresql://user:pass@host/dbname` |
| `EXPMS_STORAGE_TYPE` | `local` | `local` or `r2` |
| `EXPMS_UPLOAD_DIR` | `../data/uploads` | Used when `EXPMS_STORAGE_TYPE=local` |
| `EXPMS_R2_ACCOUNT_ID` | *(empty)* | Used when `EXPMS_STORAGE_TYPE=r2` |
| `EXPMS_R2_ACCESS_KEY_ID` | *(empty)* | R2 API token access key |
| `EXPMS_R2_SECRET_ACCESS_KEY` | *(empty)* | R2 API token secret |
| `EXPMS_R2_BUCKET_NAME` | *(empty)* | Target bucket |
| `EXPMS_R2_PREFIX` | `SUNLEASE` | Root key prefix all uploads are stored under in the bucket |
| `EXPMS_MAX_UPLOAD_SIZE_MB` | `15` | |
| `EXPMS_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |

Copy `.env.example` to `.env` and fill in real values. `.env` is
gitignored — never commit it.

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
  -v $(pwd)/data:/data \
  expms:latest
```

## Storage backends

Files are organized as `<project-code>/<year>/<month>/W<week>/<uuid4>.<ext>`
under either the local upload dir or, for R2, under the `EXPMS_R2_PREFIX`
root folder in the bucket — same layout either way.

### Local (default, good for dev / single-server deployments)

```
EXPMS_STORAGE_TYPE=local
EXPMS_UPLOAD_DIR=../data/uploads
```

No further setup — the directory is created automatically on first run.

### Cloudflare R2 (recommended for production — S3-compatible object storage)

1. In the [Cloudflare dashboard](https://dash.cloudflare.com/), go to **R2**
   and create a bucket.
2. **Manage R2 API Tokens → Create API Token**, with **Object Read & Write**
   permission scoped to that bucket. Note the Access Key ID and Secret
   Access Key shown (the secret is only shown once).
3. Copy the **Account ID** from the R2 overview page.
4. Set:
   ```
   EXPMS_STORAGE_TYPE=r2
   EXPMS_R2_ACCOUNT_ID=<account-id-from-step-3>
   EXPMS_R2_ACCESS_KEY_ID=<access-key-id-from-step-2>
   EXPMS_R2_SECRET_ACCESS_KEY=<secret-access-key-from-step-2>
   EXPMS_R2_BUCKET_NAME=<bucket-name-from-step-1>
   EXPMS_R2_PREFIX=SUNLEASE
   ```
5. Verify: `python -c "from app.services.storage import get_storage; get_storage()"`
   from `backend/` — no exception means it connected.

Switching backends does **not** migrate existing files — old files stay
wherever they were written; only new uploads follow the new setting.

## Railway deployment

1. Push the repo to GitHub. Railway auto-detects the `Dockerfile`.
2. **New Project → Deploy from GitHub repo**, select this repo.
3. **Variables** — set at minimum:
   ```
   EXPMS_SECRET_KEY=<openssl rand -hex 32>
   EXPMS_DATABASE_URL=sqlite:////data/expms.db
   EXPMS_CORS_ORIGINS=https://your-railway-domain
   ```
   For R2 storage, also set `EXPMS_STORAGE_TYPE=r2` and the `EXPMS_R2_*`
   variables from the R2 setup steps above — no file mounts needed, R2 auth
   is entirely env-var based.
4. **Volumes** — add a volume mounted at `/data` so the SQLite database
   (and local uploads, if using `EXPMS_STORAGE_TYPE=local`) survive
   redeploys. For production-grade Postgres instead, add Railway's
   PostgreSQL plugin and point `EXPMS_DATABASE_URL` at it.
5. Push to `main` — Railway redeploys automatically. First deploy: run
   `python -m app.seed` once via the Railway terminal to create the initial
   users.
6. Optional: **Settings → Domain → Add Custom Domain**, then add the CNAME
   Railway gives you at your DNS provider. SSL is automatic.

### Troubleshooting

| Symptom | Fix |
|---|---|
| Deploy fails at build | Check `Dockerfile` is at repo root and `backend/requirements.txt` is valid |
| SQLite resets on every deploy | Volume isn't mounted at `/data` |
| `ValueError: EXPMS_R2_*` missing | One of the required R2 env vars isn't set |
| `403`/`404` from R2 | Bucket name mismatch, or the API token isn't scoped to that bucket |
| CORS errors in the browser | `EXPMS_CORS_ORIGINS` doesn't include the frontend's actual origin |

### Health check

Both the Dockerfile and Railway hit `GET /api/v1/health` to determine
container health.
