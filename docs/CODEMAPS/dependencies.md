# Dependencies

## External Services

| Service | Usage | Config |
|---------|-------|--------|
| Gemini 2.5 Flash | Image classification (vision), location page detection (text), location resolution (text) | `GEMINI_API_KEY`, `MAX_CONCURRENT_GEMINI=15`, `CRAWL_CONCURRENCY=5` |
| Redis | Celery broker + result backend | `REDIS_URL` |
| PostgreSQL | Primary data store (projects, images, downloads, sessions) | `DATABASE_URL` |
| Railway | Deployment (single web container + Redis + PostgreSQL + volume) | `railway.toml`, `start.sh`, `nixpacks.toml` |

## Key Python Packages

| Package | Version | Usage |
|---------|---------|-------|
| `fastapi` | >=0.104.0 | Web framework |
| `uvicorn[standard]` | >=0.24.0 | ASGI server |
| `celery[redis]` | >=5.3.0 | Task queue |
| `Pillow` | >=10.1.0 | Image processing, overlay rendering |
| `numpy` | >=1.24.0 | Array operations for overlay position analysis |
| `scipy` | >=1.11.0 | Sobel convolution for gradient magnitude scoring |
| `imagehash` | >=4.3.1 | Perceptual hashing for deduplication |
| `google-generativeai` | >=0.8.0 | Gemini API SDK |
| `psycopg2-binary` | >=2.9.0 | PostgreSQL driver with `ThreadedConnectionPool`, exponential backoff retry |
| `requests` | >=2.31.0 | HTTP client for crawling |
| `beautifulsoup4` | >=4.12.0 | HTML parsing |
| `lxml` | >=4.9.0 | XML/sitemap parsing |
| `playwright` | >=1.40.0 | JS-rendered page crawling (optional) |
| `python-slugify` | >=8.0.1 | Filename generation |
| `itsdangerous` | >=2.1.0 | Session cookie signing (URLSafeSerializer) |
| `httpx` | >=0.25.0 | Async HTTP client |
| `redis` | >=5.0.0 | Redis client for health checks and cache |

## Internal Service Dependencies

```
crawler.py          → requests, beautifulsoup4, lxml, playwright, threading, redis (20MB download limit, SSRF protection)
                      DomainRateLimiter (Redis atomic Lua sliding window for cross-worker rate limiting, falls back to in-process threading.Lock)
                      _make_session() (creates requests.Session with retry adapter)
                      crawl_page_batch() (batch page crawling for ThreadPoolExecutor)
                      Persistent Playwright browser: reuses one Chromium instance, max 2 concurrent pages
                      Returns page metadata (title, meta_description) alongside image URLs
image_processor.py  → Pillow (MAX_IMAGE_PIXELS=50M), imagehash
                      Explicit Image.close() in all functions to prevent file descriptor leaks
gemini_client.py    → google-generativeai, redis (Redis-based distributed semaphore with TTL auto-release + atomic Lua acquire/release, falls back to local threading.Semaphore)
                      _call_with_retry: jitter + Retry-After header parsing, backoff capped at 30s
                      classify_batch: chunked processing in MAX_CONCURRENT_GEMINI-sized batches
                      detect_location_pages (batch AI location detection, ~40 pages/call)
                      classify_image (image → keyword matching)
                      resolve_location (ambiguous location → City, State)
overlay_renderer.py → Pillow, numpy, scipy (entropy+gradient position scoring, pill-shaped bars)
                      Per-thread font cache via threading.local() — avoids sharing FreeTypeFont across threads
                      _analyze_regions() downsamples to 800px before NumPy/SciPy processing
zip_builder.py      → python-slugify, models.py (in-memory ZIP build, writes to disk; caller (generate_overlays) handles db commit and failure cleanup)
cleanup.py          → models.py, filesystem
                      TOCTOU-safe: uses try/except FileNotFoundError instead of exists-then-remove
location_resolver.py → gemini_client.py (32 hardcoded unambiguous cities + STATE_NAMES dict (50 states) + extract_location_from_text() with regex patterns for page metadata fallback + Gemini fallback)
```

## Bundled Assets

- **17 TTF font files** (~4.3 MB) in `app/static/fonts/`
- 9 Google Font families: Montserrat, Poppins, Oswald, Roboto, Playfair Display, Lato, Bebas Neue, Raleway, Nunito
