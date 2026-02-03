from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.db import get_engine
from src.api.models import Base
from src.api.routes_testplan import router as testplan_router

openapi_tags = [
    {
        "name": "Health",
        "description": "Service health and diagnostics.",
    },
    {
        "name": "Test Plans",
        "description": "Import and retrieve test suites/test cases.",
    },
]

app = FastAPI(
    title="Test Item Classifier Backend",
    description="Backend API for importing WiFi test plans (CSV/XLSX) and serving suites/test cases.",
    version="0.2.0",
    openapi_tags=openapi_tags,
)

# CORS notes:
# - Browsers disallow `Access-Control-Allow-Origin: *` together with credentials.
# - Even when we don't explicitly send credentials, many environments prefer explicit origins.
#
# Env override:
# - BACKEND_CORS_ORIGINS: comma-separated list of allowed origins.
#   Example: "http://localhost:3000,https://your-preview-host"
import os

_default_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Kavia/preview environments may run on different hostnames; allow same-host frontend ports too.
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]
_env_origins = os.getenv("BACKEND_CORS_ORIGINS", "").strip()
allow_origins = (
    [o.strip() for o in _env_origins.split(",") if o.strip()] if _env_origins else _default_cors_origins
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup_create_tables() -> None:
    """
    Create database tables if they do not exist.

    Uses MYSQL_* environment variables for connection. If not set, startup may fail.
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


@app.get("/", tags=["Health"], summary="Health check", operation_id="health_check")
def health_check():
    """Simple health check endpoint."""
    return {"message": "Healthy"}


app.include_router(testplan_router)
