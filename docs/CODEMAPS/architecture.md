# Architecture Overview

## System Diagram

```
React SPA (TypeScript, Vite, Tailwind CSS, shadcn/ui)
  ↓ JSON API (fetch)
FastAPI (main.py) → JSON responses
  ↓
Routes (6 modules)     Static (built React app + Fonts)
  ↓
Services (8 modules) ←→ PostgreSQL (pooled)
  ↓
Celery Tasks (in-container via start.sh) → Redis (broker + result backend)
  ↓
External: Gemini 2.5 Flash API
```

## Request Flow (3-Step UI)

```
User → Form Submit (React)
  → POST /api/projects → create_project() → DB
  → celery.delay(process_pipeline)
  → React Query polls /api/projects/{id}/status every 3s
  → Pipeline: Crawl → AI Location Detection → Classify → Generate Previews
  → Pipeline complete → user reviews all images on single page
  → POST /api/projects/{id}/confirm → celery.delay(generate_overlays)
  → In-memory overlay + ZIP → disk write → GET /api/projects/{id}/download
```

**Steps:** Setup → Review → Download

## Service Boundaries

| Boundary | Protocol | Auth |
|----------|----------|------|
| Browser → FastAPI | HTTP/JSON | Signed session cookie (itsdangerous) |
| FastAPI → Celery | Redis broker | Internal |
| Celery → Gemini | HTTPS REST | API key |
| FastAPI → PostgreSQL | TCP (psycopg2 pool) | Internal |
| Celery → Disk/DB | File I/O + SQL | Internal (same container, shared `/data` volume) |

## Data Storage

- **PostgreSQL**: Projects, images (with page_title/meta), downloads (metadata + `zip_path`), sessions
- **Disk** (`/data/uploads/`): Original fetched/uploaded images (temporary)
- **Disk** (`/data/processed/`): Overlaid preview images (temporary)
- **Disk** (`/data/downloads/`): ZIP files (24h TTL, cleaned by Celery beat)

## Concurrency Model

- **Web**: Single uvicorn process, async request handling
- **Workers**: Celery prefork pool (4 workers) running in-container via `start.sh`, CPU-bound image processing, `broker_connection_retry_on_startup=True`
- **Crawler**: ThreadPoolExecutor (`CRAWL_CONCURRENCY`, default 5) with `DomainRateLimiter` (Redis sliding window for cross-worker rate limiting, falls back to in-process `threading.Lock`); persistent Playwright browser reused across pages (max 2 concurrent pages)
- **Gemini API**: Redis-based distributed semaphore (`_DistributedSemaphore`) with per-slot TTL auto-release (2 min crash safety) and atomic Lua acquire/release scripts, falls back to local `threading.Semaphore`; retry with jitter + `Retry-After` header parsing, backoff capped at 30s; `classify_batch` processes images in chunks of `MAX_CONCURRENT_GEMINI` to limit memory
- **PostgreSQL**: ThreadedConnectionPool (1-10 connections), initialized with `_retry_with_backoff()` helper (exponential backoff + jitter, 5 max attempts, 2s base delay, 30s max)
- **Font cache**: Per-thread via `threading.local()` in `overlay_renderer.py` (avoids sharing FreeTypeFont objects across threads)

## Security

- **Session ownership**: All route endpoints verify `session_id` matches project owner (`require_project_ownership()`)
- **Path traversal prevention**: `safe_path()` helper validates file paths stay within allowed directories
- **SSRF prevention**: `_assert_safe_url()` blocks private/loopback IPs in crawler
- **Input validation**: Route handlers enforce max 500 chars on keyword/location, status allowlist in api.py, `images_per_page` clamped 1-50 in project.py
- **Cookie security**: HttpOnly, Secure, SameSite=Lax signed cookies

## Robustness

- **Stale task detection**: Status polling endpoints detect tasks stuck in PENDING for >30 minutes; marks projects as failed
- **Celery result TTL**: 24 hours (matches file retention)
- **Image download limit**: 20MB max per image (streamed), PIL decompression capped at 50MP
- **Gemini resilience**: Specific exception type handling with structured retry logic; batch fails if 0 images classified
- **Pipeline validation**: Unified pipeline checks for empty results at each stage with diagnostic error messages
- **Auto-skip**: Images with confidence < 0.4 auto-deselected (status `auto_skipped`), restorable by user
- **Session middleware**: Gracefully handles DB errors to prevent session failures from blocking requests
- **Input validation**: `ValueError` guards on dynamic SQL column names (`isidentifier()` + allowlist in models.py); route handlers validate `int()` casts
- **Resource cleanup**: Celery tasks use `try/except/finally` with `db.rollback()` in except blocks and `return_db(db)` in finally blocks; `db_dependency()` auto-rolls back uncommitted state
- **Resource limits**: `MAX_IMAGES_PER_PROJECT=500`, `MAX_PAGES_TO_CRAWL=200` cap crawl volume
- **Double enqueue prevention**: `confirm_review` uses atomic `UPDATE ... WHERE status IN (...)` via `update_project_status_if()` to transition to `generating`; returns 409 Conflict before any task is dispatched if the atomic transition fails (race-safe)
- **Streaming downloads**: ZIP download route uses `FileResponse` to serve disk-based ZIP files (sync `def`, not `async def`)
- **Overlay analysis downsampling**: `_analyze_regions()` downsamples images to max 800px before NumPy/SciPy processing (~25x memory reduction)
- **Image resource management**: Explicit `Image.close()` in all `image_processor.py` functions to prevent file descriptor leaks
- **TOCTOU-safe cleanup**: `cleanup.py` uses try/except `FileNotFoundError` instead of exists-then-remove pattern
