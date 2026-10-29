# Contributing

## Prerequisites

- Python 3.11+
- Node.js 18+
- Redis (local or Docker)
- PostgreSQL (local or Docker)

## Dev Setup

See the **Running it locally** section in [`README.md`](../README.md#running-it-locally) for setup instructions (backend, frontend, PostgreSQL, Redis, Celery).

## Code Style

- Backend: Python, follow existing patterns in `app/`
- Frontend: TypeScript, Tailwind CSS utility classes, shadcn/ui components
- All API routes use `/api` prefix
- Long-running operations go through Celery tasks, never block request handlers

## Implementation Rules

1. **Never block FastAPI request handlers.** All crawling, classification, and overlay generation must go through Celery tasks. The frontend polls for progress.

2. **Gemini rate limiting is essential.** Concurrency is capped at `MAX_CONCURRENT_GEMINI` by a Redis-backed distributed semaphore (local semaphore fallback). Back off exponentially with jitter on 429/5xx and honor Retry-After. Stay at 90% of the published rate limit.

3. **Image deduplication must happen before classification** to avoid wasting Gemini API calls on duplicate images.

4. **Font files are bundled in the repo** (`app/static/fonts/`). Never load fonts from external URLs at render time.

5. **Overlay renderer is CPU-bound.** Use Celery's concurrency (prefork pool) to parallelize across worker processes.

6. **Crawl respectfully.** Always respect robots.txt. Use a descriptive User-Agent. Rate limit to 1 req/sec per domain. 10-second timeout per request.

7. **Database is PostgreSQL.** Connection pool with exponential backoff + jitter retry on startup.

8. **Session cookie security:** Sign with SECRET_KEY. Use HttpOnly, Secure and SameSite=Lax flags. Cookie value maps to sessions table.

9. **File cleanup must be reliable.** Celery beat runs cleanup every hour. Also clean on app startup for files missed while app was down.

10. **Partial failure is OK.** Every pipeline stage (crawl, classify, overlay) can partially fail. Track per-image status in DB. If 3 of 200 images fail, the other 197 should still be in the ZIP. Surface errors clearly but don't block the batch.

## Testing

End-to-end tests use Playwright (`e2e/`, 8 tests in 5 spec files): health check, setup form, full crawl→review→generate→download flow with ZIP validation (magic bytes, JPEG count, `manifest.csv`), projects dashboard, and download regression.

    cd e2e && npm ci && npx playwright install chromium
    E2E_BASE_URL=http://localhost:8000 E2E_SITE_URL=https://your-test-site.example npx playwright test

`E2E_CLIENT_NAME` and `E2E_SITE_URL` override the placeholder project used by the full-flow test; point `E2E_SITE_URL` at a site you are allowed to crawl.

## PR Checklist

- [ ] Code follows existing project patterns
- [ ] No hardcoded secrets or API keys
- [ ] All user inputs validated
- [ ] Long operations use Celery tasks (not blocking)
- [ ] Frontend builds successfully (`cd frontend && npm run build`)
- [ ] Backend starts without errors (`uvicorn app.main:app`)
- [ ] Health check passes (`GET /health`)
