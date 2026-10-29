"""PostgreSQL database initialization and connection management."""

import logging
import random
import threading
import time
from typing import Callable, TypeVar

import psycopg2
import psycopg2.extras
import psycopg2.pool

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

MAX_RETRY_ATTEMPTS = 5
RETRY_BASE_DELAY = 2  # seconds
MAX_RETRY_DELAY = 30  # seconds

T = TypeVar("T")


def _retry_with_backoff(
    fn: Callable[[], T],
    label: str,
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY,
) -> T:
    """Execute *fn* with exponential backoff + jitter on OperationalError."""
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except psycopg2.OperationalError as e:
            if attempt == max_attempts:
                logger.error("%s failed after %d attempts: %s", label, max_attempts, e)
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), MAX_RETRY_DELAY)
            jitter = random.uniform(0, delay * 0.2)
            logger.warning(
                "%s attempt %d/%d failed: %s. Retrying in %.1fs...",
                label, attempt, max_attempts, e, delay + jitter,
            )
            time.sleep(delay + jitter)
    raise RuntimeError("Unreachable: exhausted retry loop")


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Return the global connection pool, creating it on first call.

    Uses double-checked locking for thread-safe lazy initialization.
    """
    global _pool
    if _pool is None or _pool.closed:
        with _pool_lock:
            if _pool is None or _pool.closed:
                _pool = _retry_with_backoff(
                    lambda: psycopg2.pool.ThreadedConnectionPool(
                        minconn=1, maxconn=10, dsn=DATABASE_URL
                    ),
                    "Pool creation",
                )
    return _pool


def init_db():
    """Create tables if they don't exist."""
    conn = _retry_with_backoff(lambda: psycopg2.connect(DATABASE_URL), "DB init")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    client_name TEXT,
                    website_url TEXT,
                    keywords TEXT NOT NULL,
                    locations TEXT,
                    font TEXT NOT NULL DEFAULT 'Montserrat',
                    images_per_page INTEGER DEFAULT 1,
                    fetch_anywhere BOOLEAN DEFAULT FALSE,
                    js_rendered BOOLEAN DEFAULT FALSE,
                    status TEXT DEFAULT 'setup',
                    celery_task_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project_images (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    source_url TEXT,
                    source_page_url TEXT,
                    location TEXT,
                    keyword TEXT,
                    image_hash TEXT,
                    classification TEXT,
                    confidence DOUBLE PRECISION,
                    overlay_position TEXT,
                    original_path TEXT,
                    processed_path TEXT,
                    status TEXT DEFAULT 'pending',
                    width INTEGER,
                    height INTEGER,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    client_name TEXT,
                    image_count INTEGER,
                    zip_path TEXT,
                    zip_size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
        conn.commit()

        # Migrations
        with conn.cursor() as cur:
            # Remove zip_data blob column — files live on shared volume only
            cur.execute("""
                ALTER TABLE downloads DROP COLUMN IF EXISTS zip_data
            """)
            # Add page metadata columns
            cur.execute("""
                ALTER TABLE project_images ADD COLUMN IF NOT EXISTS page_title TEXT
            """)
            cur.execute("""
                ALTER TABLE project_images ADD COLUMN IF NOT EXISTS page_meta_description TEXT
            """)
        conn.commit()
    finally:
        conn.close()


def get_db():
    """Return a connection from the pool with RealDictCursor."""
    conn = _get_pool().getconn()
    conn.autocommit = False
    return conn


def return_db(conn):
    """Return a connection to the pool.

    Rolls back uncommitted state and resets autocommit before returning.
    If the pool rejects the connection, close it to prevent TCP leaks.
    """
    try:
        conn.rollback()
        conn.autocommit = False
        _get_pool().putconn(conn)
    except Exception as exc:
        logger.error("Failed to return connection to pool: %s", exc)
        try:
            conn.close()
        except Exception as close_exc:
            logger.warning("Failed to close connection: %s", close_exc)


def db_dependency():
    """FastAPI dependency that yields a pooled DB connection."""
    conn = get_db()
    try:
        yield conn
    finally:
        return_db(conn)
