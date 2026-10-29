# Data Architecture

## Database: PostgreSQL

Connection: `psycopg2.pool.ThreadedConnectionPool` (1-10 connections)
Resilience: `_retry_with_backoff()` helper with exponential backoff + jitter (max 5 attempts, 2s base delay, 30s max)
Config: `DATABASE_URL` env var (default: `postgresql://localhost/gbp_overlay`)

## Tables

### sessions
```
session_id TEXT PK
created_at TIMESTAMP
last_seen_at TIMESTAMP
```

### projects
```
id SERIAL PK
session_id TEXT FK → sessions
client_name TEXT
website_url TEXT
keywords TEXT (JSON array)
locations TEXT (JSON array, nullable)
font TEXT DEFAULT 'Montserrat'
images_per_page INTEGER DEFAULT 1
fetch_anywhere BOOLEAN DEFAULT FALSE
js_rendered BOOLEAN DEFAULT FALSE
status TEXT DEFAULT 'setup'  -- setup → processing → review → generating → complete | failed
celery_task_id TEXT
created_at TIMESTAMP
```

### project_images
```
id SERIAL PK
project_id INTEGER FK → projects
source_url TEXT
source_page_url TEXT
location TEXT
keyword TEXT
image_hash TEXT (perceptual hash)
classification TEXT (Gemini result)
confidence DOUBLE PRECISION (0-1)
overlay_position TEXT (bottom-center, top-center, etc.)
original_path TEXT
processed_path TEXT
status TEXT DEFAULT 'pending'  -- pending → classified → confirmed → overlaid | skipped | duplicate | auto_skipped
width INTEGER
height INTEGER
page_title TEXT                  -- extracted during crawl
page_meta_description TEXT       -- extracted during crawl
```

### downloads
```
id SERIAL PK
project_id INTEGER FK → projects
session_id TEXT FK → sessions
client_name TEXT
image_count INTEGER
zip_path TEXT (filesystem path)
zip_size INTEGER
created_at TIMESTAMP
expires_at TIMESTAMP
```

## Relationships

```
sessions 1 → N projects
projects 1 → N project_images
projects 1 → N downloads
sessions 1 → N downloads
```

## File Storage

| Directory | Contents | Retention |
|-----------|----------|-----------|
| `/data/uploads/{project_id}/` | Original images (fetched/uploaded) | 24h |
| `/data/processed/{project_id}/` | Preview overlaid images | 24h |
| `/data/downloads/` | ZIP files (disk-only storage) | 24h |

**ZIP Storage Strategy:**
- `zip_builder.py` assembles ZIPs in-memory (`BytesIO`), then performs an atomic disk write to `/data/downloads/`
- The `downloads` table stores **metadata only** (`zip_path`, `zip_size`), NOT file content — there is no BLOB column
- Download route serves files via `FileResponse` (sync `def`, not `async def`)
- Single-container deployment (`start.sh`) ensures uvicorn and celery share the `/data` volume without cross-service mounting

**Cleanup:** Celery beat task (`cleanup_expired_task`) runs hourly and also on app startup (see `app/main.py` lifespan).

## Status Transitions

```
Project: setup → processing → review → generating → complete
                    ↓           ↓          ↓
                  failed      failed      failed
              (crash/stuck detected after 30min by status polling endpoints)

Intermediate statuses (crawling, crawled, classifying, matching, previewing) are also accepted
  → All treated as equivalent to "processing" or "review" by the review route

Image:   pending → classified → confirmed → overlaid
                 → auto_skipped (confidence < 0.4 or no keyword match)
                 → skipped (user-excluded or file error)
         pending → duplicate (dedup phase)

auto_skipped → classified (restored via PATCH /api/images/{id}/restore)
```

## Error Recovery

- Stale tasks (PENDING > 30 minutes) auto-detected by status polling endpoints and marked failed
- Celery results retained for 24 hours (matches file retention)
- `db_dependency()` yields connection; `return_db()` calls `conn.rollback()` to clean uncommitted state before returning to pool
- Celery tasks use `try/except/finally`: `db.rollback()` in except blocks, `return_db(db)` in finally blocks
- Model CRUD helpers no longer auto-commit; callers control transaction boundaries with explicit `db.commit()`
- `update_project_status_if()`: Atomic conditional status transition using `UPDATE ... WHERE status IN (...)`. Returns row count (0 = no transition). Used by `confirm_review` to prevent double-enqueue races.
- Unified pipeline validates non-empty results at each stage with diagnostic error messages
- `generate_overlays` provides specific diagnostic messages when 0 images qualify (all duplicates, no keywords, no locations, etc.)
