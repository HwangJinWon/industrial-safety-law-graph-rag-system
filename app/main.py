"""Single FastAPI entrypoint for Graph-RAG and operations APIs."""

import hmac
import os

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.routing import APIRoute

from graph_rag_pipeline.ask_adapter import app as graph_rag_app
from operations_api.router import router as operations_router
from operations_api.storage import initialize_database


app = FastAPI(
    title="Industrial Safety Platform API",
    description="Law Graph-RAG plus equipment, smartwatch, attendance, and dashboard APIs.",
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

LOCAL_CORS_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5174",
    "http://localhost:5174",
]


def configured_cors_origins() -> list[str]:
    """Return local origins plus explicitly configured dashboard origins."""
    configured = os.environ.get("WORKFIT_CORS_ORIGINS", "")
    additional = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    return list(dict.fromkeys([*LOCAL_CORS_ORIGINS, *additional]))


def require_staging_api_key(provided_key: str | None = Depends(api_key_header)) -> None:
    """Require a shared key only when WORKFIT_API_KEY is configured."""
    expected_key = os.environ.get("WORKFIT_API_KEY", "").strip()
    if not expected_key:
        return
    if not provided_key or not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")


@app.get("/healthz", include_in_schema=False)
def public_healthcheck() -> dict[str, str]:
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Preserve every existing Graph-RAG API route at its original URL while keeping
# this combined app's own /docs and /openapi.json endpoints.
graph_rag_router = APIRouter()
graph_rag_router.routes.extend(
    route for route in graph_rag_app.routes if isinstance(route, APIRoute)
)
app.include_router(graph_rag_router, tags=["graph-rag"])

# Keep operational data and code independent from Neo4j/Graph-RAG.
app.include_router(operations_router, dependencies=[Depends(require_staging_api_key)])
initialize_database()
