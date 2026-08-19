from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import Base, engine
from app.models import __init__ as _models  # noqa: F401  (ensures models are registered)
from app.migrate import migrate
from app.routers import auth, masters, expenses, invoices, payments, claims, documents, dashboard, admin, edit_requests

# Additive auto-migration: creates any missing tables/columns without
# touching existing data. See app/migrate.py for exactly what this does
# and does not handle - run `python -m app.migrate` directly for a verbose
# summary after changing a model.
migrate(verbose=False)

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


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}
