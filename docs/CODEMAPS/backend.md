# Backend Architecture

## Routes → Services → DB

All routes are mounted with `/api` prefix in `main.py`. The React SPA handles client-side routing; FastAPI serves the built SPA via a catch-all route.

### Project Setup
```
POST /api/projects                 → project.create_project   → models.create_project → DB
                                     → image_processor.validate_image, compute_hash, convert_to_jpeg
                                     → clamps images_per_page to 1-50
                                     → celery: process_pipeline (or process_pipeline with skip_crawl=True)
```

### Review Pipeline
```
GET  /api/projects/{id}            → review.get_project       → project detail with images (JSON)
GET  /api/projects/{id}/status     → review.pipeline_status   → AsyncResult(task_id) multi-stage progress
POST /api/projects/{id}/confirm    → review.confirm_review    → models.update_project_image → celery: generate_overlays → models.update_project_status_if (atomic transition to "generating")
```

### Preview Image Serving
```
GET  /api/projects/{id}/images/{img_id}/preview → preview.serve_preview_image → FileResponse (falls back to original image with project_id ownership validation)
```

### Generate & Download
```
POST /api/projects/{id}/generate         → generate.start_generation   → celery: generate_overlays
GET  /api/projects/{id}/generation-status → generate.generation_status → AsyncResult(task_id)
GET  /api/projects/{id}/download         → download.download_zip       → FileResponse from disk via zip_path (sync def)
GET  /api/projects                       → download.list_projects      → models.get_session_projects + get_session_downloads (sync def)
```

### Image Editing API
```
PATCH /api/images/{id}/keyword      → api.update_image_keyword → models.update_project_image (max 500 chars)
PATCH /api/images/{id}/location     → api.update_image_location → models.update_project_image (max 500 chars)
PATCH /api/images/{id}/status       → api.update_image_status   → models.update_project_image (status allowlist: classified/confirmed/pending/skipped/auto_skipped)
PATCH /api/images/{id}/restore      → api.restore_image         → models.update_project_image (auto_skipped → classified)
```

### System
```
GET   /health                       → main.health              → DB + Redis check
GET   /{path}                       → main.spa_fallback        → serves React SPA index.html
```

## Middleware Chain

```
Request → session_middleware (signed cookie → session_id) → Route Handler → Response
```

- Reads/creates signed session cookie via `itsdangerous.URLSafeSerializer`
- Stores `session_id` on `request.state`
- Creates/updates session in DB

## Shared Helpers (deps.py)

- `require_project_ownership(project, session_id)` — 403 if session doesn't own project
- `safe_path(base, *parts)` — Path traversal prevention (400 on escape)
- `serialize_for_json(obj)` — Recursive datetime/memoryview serializer for JSON responses

## Celery Tasks

| Task | Trigger | Service Calls |
|------|---------|---------------|
| `process_pipeline` | POST /api/projects | crawler.* → image_processor.* → gemini_client.detect_location_pages → gemini_client.classify_batch → location_resolver.* → overlay_renderer.render_overlay (previews) |
| `generate_overlays` | POST /api/projects/{id}/confirm | overlay_renderer.render_overlay_bytes → zip_builder (in-memory) → disk write → models.create_download (failure cleanup deletes orphan ZIP) |
| `cleanup_expired` | Beat (hourly) | cleanup.run_cleanup |

**`STAGE_WEIGHTS`** (module-level constant in `crawl_tasks.py`): `{1: (0, 40), 2: (40, 50), 3: (50, 80), 4: (80, 100)}`

### Unified Pipeline Stages (`process_pipeline`)

| Stage | Progress % | Description |
|-------|-----------|-------------|
| Crawling | 0-40% | Fetch sitemap, crawl pages, download images, dedup, extract page titles/meta |
| Location Detection | 40-50% | Batch Gemini call for AI-powered location page identification |
| Classifying | 50-80% | Gemini image classification (single-keyword shortcut: auto-assign) |
| Resolving & Previews | 80-100% | Resolve locations (URL slug + page metadata text fallback), generate ALL preview overlays (progress reported every 10 images) |

## Key Files

| File | Lines | Role |
|------|-------|------|
| `app/main.py` | ~166 | Entry point, session middleware, 6 router mounts, lifespan startup/shutdown, SPA catch-all |
| `app/config.py` | ~64 | Env vars, font config, directory setup, `STALE_TASK_MINUTES` constant |
| `app/database.py` | ~187 | PostgreSQL pool, `_retry_with_backoff()`, init_db, migrations (page_title, page_meta_description) |
| `app/models.py` | ~306 | CRUD for sessions, projects, images (+ page_title/meta fields), downloads, `update_project_status_if()` atomic transition |
| `app/deps.py` | ~38 | Shared helpers: require_project_ownership, safe_path, serialize_for_json |
| `app/routes/*.py` | ~745 | HTTP endpoints across 6 modules (project, review, preview, generate, download, api) |
| `app/services/*.py` | ~1,880 | Business logic across 8 modules (entropy+gradient overlay positioning, AI location detection) |
| `app/tasks/*.py` | ~756 | Celery tasks across 3 modules (unified pipeline, in-memory ZIP) |
| `app/services/overlay_renderer.py` | ~349 | Pill-shaped rounded bar, entropy+gradient+variance position scoring, min(w,h)/25 font sizing |
| `app/services/gemini_client.py` | ~425 | Redis-based distributed semaphore (`_DistributedSemaphore` with TTL auto-release, atomic Lua scripts), retry with jitter + Retry-After parsing, classify_image, chunked classify_batch (processes in `MAX_CONCURRENT_GEMINI`-sized chunks), resolve_location, detect_location_pages |
| `app/routes/review.py` | ~229 | Project detail, pipeline status polling, confirm review (atomic status transition via `update_project_status_if`) |
