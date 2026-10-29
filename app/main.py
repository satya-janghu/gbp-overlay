"""FastAPI application entry point."""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg2
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeSerializer, BadSignature
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import SECRET_KEY, SESSION_COOKIE_MAX_AGE, ensure_data_dirs
from app.database import init_db, get_db, return_db
from app.limiter import limiter
from app.models import get_or_create_session
from app.routes.project import router as project_router
from app.routes.preview import router as preview_router
from app.routes.generate import router as generate_router
from app.routes.download import router as download_router
from app.routes.api import router as api_router
from app.routes.review import router as review_router

logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent

# Signed cookie serializer
cookie_serializer = URLSafeSerializer(SECRET_KEY, salt="session")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Create data directories
    ensure_data_dirs()

    # Initialize database
    init_db()

    # Run cleanup of expired files on startup (blocking I/O in thread)
    from app.services.cleanup import run_cleanup
    await asyncio.to_thread(run_cleanup)

    yield


app = FastAPI(title="GBP Image Overlay Tool", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount static files (fonts, and SPA assets)
app.mount("/static/fonts", StaticFiles(directory=str(APP_DIR / "static" / "fonts")), name="fonts")

# Mount SPA build assets if they exist
spa_assets_dir = APP_DIR / "static" / "dist" / "assets"
if spa_assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(spa_assets_dir)), name="spa-assets")


# ---------------------------------------------------------------------------
# Session middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def session_middleware(request: Request, call_next):
    """Read or create a signed session cookie."""
    session_id = None
    is_new_session = False

    # Try to read existing cookie
    raw_cookie = request.cookies.get("session_id")
    if raw_cookie:
        try:
            session_id = cookie_serializer.loads(raw_cookie)
        except BadSignature:
            session_id = None

    # Create new session if needed
    if not session_id:
        session_id = uuid.uuid4().hex
        is_new_session = True

    # Touch session in DB
    db = get_db()
    try:
        get_or_create_session(db, session_id)
    except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        logger.error("Session middleware DB error: %s", e)
    finally:
        return_db(db)

    # Store on request state
    request.state.session_id = session_id

    response: Response = await call_next(request)

    # Set cookie if new or refresh existing
    if is_new_session:
        signed = cookie_serializer.dumps(session_id)
        response.set_cookie(
            key="session_id",
            value=signed,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=SESSION_COOKIE_MAX_AGE,
        )

    return response


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    checks = {"app": "ok"}
    # Check PostgreSQL
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        logger.warning("Health check DB error: %s", e)
        checks["database"] = "error"
    finally:
        if 'db' in locals():
            return_db(db)
    # Check Redis
    try:
        import redis as _redis
        from app.config import REDIS_URL
        r = _redis.from_url(REDIS_URL, socket_connect_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        logger.warning("Health check Redis error: %s", e)
        checks["redis"] = "error"

    all_ok = checks.get("redis") == "ok" and checks.get("database") == "ok"
    overall = "ok" if all_ok else "degraded"
    return {"status": overall, **checks}


# ---------------------------------------------------------------------------
# Include API routers with /api prefix
# ---------------------------------------------------------------------------

app.include_router(project_router, prefix="/api")
app.include_router(review_router, prefix="/api")
app.include_router(preview_router, prefix="/api")
app.include_router(generate_router, prefix="/api")
app.include_router(download_router, prefix="/api")
app.include_router(api_router, prefix="/api")


# ---------------------------------------------------------------------------
# SPA catch-all (must be last)
# ---------------------------------------------------------------------------

@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """Serve the React SPA index.html for all non-API routes."""
    index = APP_DIR / "static" / "dist" / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"error": "Frontend not built"}, status_code=404)
