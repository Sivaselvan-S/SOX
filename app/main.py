from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.mongo import init_indexes, close_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: connect to MongoDB and init indexes on startup, close on shutdown."""
    await init_indexes()
    yield
    await close_client()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
# For production: set ALLOWED_ORIGINS env var to a comma-separated list of
# allowed frontend URLs, e.g. "https://griffsox.vercel.app,https://griffsox.com"
# For local dev: falls back to permissive localhost origins.
def _get_allowed_origins() -> List[str]:
    raw = settings.ALLOWED_ORIGINS.strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    # Dev fallback — explicit localhost origins (credentials-safe, no wildcard)
    return [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "project": settings.PROJECT_NAME}


# Mount built React frontend if dist directory exists
dist_path = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if dist_path.exists():
    app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Don't intercept API or docs routes
        if full_path.startswith("api") or full_path.startswith("docs") or full_path.startswith("redoc"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        file_path = dist_path / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(dist_path / "index.html")
