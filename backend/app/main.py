import os
import sys
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.session import Base, engine
from app.models import __init__ as _models  # noqa: F401  (ensures models are registered)
from app.migrate import migrate
from app.routers import auth, masters, expenses, invoices, payments, claims, documents, dashboard, admin, edit_requests, recurring_expenses

# Additive auto-migration: creates any missing tables/columns without
# touching existing data. See app/migrate.py for exactly what this does
# and does not handle - run `python -m app.migrate` directly for a verbose
# summary after changing a model.
try:
    print(f"[STARTUP] Running database migration...")
    print(f"[STARTUP] Database URL: {settings.DATABASE_URL}")
    print(f"[STARTUP] Upload Dir: {settings.UPLOAD_DIR}")
    migrate(verbose=True)
    print(f"[STARTUP] Migration completed successfully")
except Exception as e:
    print(f"[ERROR] Migration failed: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

app = FastAPI(title=settings.APP_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(masters.router)
app.include_router(expenses.router)
app.include_router(invoices.router)
app.include_router(payments.router)
app.include_router(claims.router)
app.include_router(documents.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(edit_requests.router)
app.include_router(recurring_expenses.router)


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}


# Serve the built frontend (Dockerfile copies the Vite build output here).
# All API routes live under /api/v1, so it's safe to catch everything else
# and fall back to index.html for client-side routing.
_frontend_dist = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend_dist")
if os.path.isdir(_frontend_dist):
    print(f"[STARTUP] Frontend dist found at: {_frontend_dist}")
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="frontend-assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        candidate = os.path.join(_frontend_dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_frontend_dist, "index.html"))
else:
    print(f"[WARNING] Frontend dist NOT found at: {_frontend_dist}")

