# Runbook

## Deployment

**Platform:** Railway.com

**Services:**
| Service | Process | Config |
|---------|---------|--------|
| Web | `bash start.sh` (uvicorn + celery in one container) | `railway.toml` (`startCommand`) |
| Redis | Railway managed | Provides `REDIS_URL` |
| PostgreSQL | Railway managed | Provides `DATABASE_URL` |

**Volume:** Mounted at `/data` on the Web service. The single-container model ensures uvicorn and celery share the same volume without cross-service mounting.

**Build:** Nixpacks builder. `railway.toml` specifies `buildCommand = "pip install -r requirements.txt"`. `nixpacks.toml` adds `postgresql_16.dev` for `psycopg2-binary`.

**Startup:** `start.sh` launches celery (background) and uvicorn (foreground). If either process exits, the other is killed and the container restarts. No sleep delay needed — database retry logic handles readiness (`_retry_with_backoff()`, `broker_connection_retry_on_startup=True`).

## Health Check

```
GET /health
```

Returns:
```json
{
  "status": "ok",       // or "degraded"
  "app": "ok",
  "database": "ok",     // or "error: <message>"
  "redis": "ok"         // or "error: <message>"
}
```

Railway health check timeout: 300 seconds.

## Common Issues

### Redis Connection Failure
- **Symptom:** Health check shows `redis: error`, Celery tasks not processing
- **Fix:** Verify `REDIS_URL` env var is set correctly. Check Railway Redis service status.

### Celery Worker Not Running
- **Symptom:** Projects stuck in "crawling" or "generating" status indefinitely
- **Fix:** Check Railway Web service logs (celery runs inside the same container via `start.sh`). Look for celery-specific log lines. Ensure `REDIS_URL` and `DATABASE_URL` are set. Worker uses `broker_connection_retry_on_startup=True` so transient Redis issues self-heal. If celery crashes, `start.sh` detects the exit and restarts the entire container.

### Crawl Performance Tuning
- **Symptom:** Crawling stage takes too long for sites with many pages
- **Fix:** Increase `CRAWL_CONCURRENCY` env var (default: 5). Pages are crawled concurrently using a ThreadPoolExecutor with per-domain rate limiting (1 req/sec). Higher concurrency helps when crawling across multiple domains. Monitor memory usage when increasing beyond 10.

### Gemini API Rate Limits
- **Symptom:** Classification tasks slow or failing with 429 errors
- **Fix:** Lower `MAX_CONCURRENT_GEMINI` env var (default: 15). The client uses a Redis-based distributed semaphore to enforce the limit across all workers. Retry includes jitter + Retry-After header parsing with backoff capped at 30s. Falls back to local threading.Semaphore if Redis is unavailable.

### Database Connection Issues
- **Symptom:** Health check shows `database: error`, requests failing
- **Fix:** The web service uses `_retry_with_backoff()` with exponential backoff + jitter (5 attempts, 2s base, 30s max). If persistent, check Railway PostgreSQL service status and `DATABASE_URL`.

### Stale Tasks
- **Symptom:** Projects stuck in processing state
- **Details:** Status polling endpoints detect tasks stuck in PENDING for >30 minutes and mark projects as failed (`STALE_TASK_MINUTES` in `config.py`).

### Frontend Not Loading
- **Symptom:** `GET /` returns `{"error": "Frontend not built"}`
- **Fix:** Run `cd frontend && npm run build` to generate `app/static/dist/`. The built assets must be committed to the repo (Railway build only runs `pip install`).

### Resource Limits
- `MAX_IMAGES_PER_PROJECT` (default: 500) — caps images crawled per project
- `MAX_PAGES_TO_CRAWL` (default: 200) — caps sitemap pages crawled per project
- All configurable via environment variables (see `app/config.py`)

### Double Enqueue Prevention
- **Symptom:** User clicks "Confirm" multiple times rapidly, causing duplicate generation tasks
- **Behavior:** The `confirm_review` endpoint uses `update_project_status_if()` — an atomic `UPDATE ... WHERE status IN (...)` — to transition to `generating`. If the atomic transition fails (row count 0), 409 Conflict is returned before any task is dispatched. This is race-safe even under concurrent requests.

## File Cleanup

- Celery beat runs `cleanup_expired` task every hour
- Deletes ZIP downloads older than `FILE_RETENTION_HOURS` (default: 24h)
- Cleans orphaned files in `uploads/` and `processed/` directories
- Also runs on app startup to catch files missed while app was down

## Rollback

Use the Railway dashboard to roll back to a previous deployment:
1. Go to the service in Railway dashboard
2. Click on Deployments
3. Select a previous successful deployment
4. Click "Rollback"

Database migrations are forward-only (applied in `init_db()`). If a rollback is needed after a schema change, manual SQL intervention may be required.

## Monitoring

- **Health endpoint:** `GET /health` — checks app, database, and Redis
- **Celery task status:** Polled by frontend via `/api/projects/{id}/status` and `/api/projects/{id}/generation-status`
- **Railway logs:** Available in Railway dashboard for the Web service (contains both uvicorn and celery output)
