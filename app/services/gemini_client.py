"""Gemini AI integration for image classification and location resolution."""
import json
import random
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.config import GEMINI_API_KEY, GEMINI_MOCK, MAX_CONCURRENT_GEMINI, REDIS_URL

logger = logging.getLogger(__name__)

# ---------- Distributed rate limiting via Redis ----------
# Falls back to a local threading.Semaphore when Redis is unavailable.

_local_semaphore = threading.Semaphore(int(MAX_CONCURRENT_GEMINI))
_redis_client = None
_redis_init_lock = threading.Lock()
_REDIS_SEMAPHORE_KEY = "gemini:semaphore"
_REDIS_SEMAPHORE_TTL = 120  # auto-release after 2 min (crash safety)


def _get_redis():
    """Lazy-init a shared Redis client (returns None on failure)."""
    global _redis_client
    if _redis_client is None:
        with _redis_init_lock:
            if _redis_client is None:
                try:
                    import redis
                    _redis_client = redis.Redis.from_url(
                        REDIS_URL, socket_connect_timeout=2, decode_responses=True,
                    )
                    _redis_client.ping()
                except Exception as e:
                    logger.warning("Redis unavailable for Gemini rate-limit; falling back to local semaphore: %s", e)
                    _redis_client = False  # sentinel: don't retry
    return _redis_client if _redis_client is not False else None


# Lua script for atomic semaphore acquire: check count < max, then incr + set slot key
_ACQUIRE_LUA = """\
local current = tonumber(redis.call('get', KEYS[1]) or '0')
if current < tonumber(ARGV[1]) then
    redis.call('incr', KEYS[1])
    redis.call('set', KEYS[2], '1', 'EX', tonumber(ARGV[2]))
    return 1
else
    return 0
end
"""

# Lua script for atomic semaphore release: delete slot, decr counter, floor at 0
_RELEASE_LUA = """\
redis.call('del', KEYS[2])
local val = redis.call('decr', KEYS[1])
if val < 0 then
    redis.call('set', KEYS[1], '0')
end
return 1
"""


class _DistributedSemaphore:
    """Cross-worker semaphore backed by a Redis counter with TTL-based expiry.

    Each acquire increments the counter; release decrements it.
    A per-slot key with TTL ensures slots are reclaimed if a worker crashes.
    Falls back to a local threading.Semaphore when Redis is unreachable.

    Per-call state is stored in thread-local storage to avoid data races
    when multiple threads share the same singleton instance.
    """

    def __init__(self, max_concurrent: int):
        self._max = max_concurrent
        self._local = threading.Semaphore(max_concurrent)
        self._tls = threading.local()

    def _acquire_redis(self, r) -> str | None:
        """Try to claim a slot via atomic Lua script. Returns a unique token or None."""
        token = f"{threading.get_ident()}:{time.monotonic_ns()}"
        slot_key = f"{_REDIS_SEMAPHORE_KEY}:slot:{token}"

        try:
            # Redis EVAL runs Lua atomically — no TOCTOU race
            result = r.eval(  # noqa: S307 — Redis EVAL, not Python eval
                _ACQUIRE_LUA, 2,
                _REDIS_SEMAPHORE_KEY, slot_key,
                self._max, _REDIS_SEMAPHORE_TTL,
            )
            return token if result == 1 else None
        except Exception:
            return None

    def _release_redis(self, r, token: str):
        """Release a slot via atomic Lua script."""
        slot_key = f"{_REDIS_SEMAPHORE_KEY}:slot:{token}"
        try:
            r.eval(_RELEASE_LUA, 2, _REDIS_SEMAPHORE_KEY, slot_key)  # noqa: S307
        except Exception:
            pass

    def __enter__(self):
        r = _get_redis()
        if r is None:
            self._local.acquire()
            self._tls.token = None
            self._tls.use_local = True
            return self

        self._tls.use_local = False
        # Spin with backoff until a slot opens
        for attempt in range(300):  # ~5 min max wait
            token = self._acquire_redis(r)
            if token:
                self._tls.token = token
                return self
            time.sleep(0.5 + random.uniform(0, 0.5))

        # Exhausted retries — fall back to local
        logger.warning("Redis semaphore contention; falling back to local")
        self._local.acquire()
        self._tls.token = None
        self._tls.use_local = True
        return self

    def __exit__(self, *_exc):
        use_local = getattr(self._tls, 'use_local', True)
        token = getattr(self._tls, 'token', None)
        if use_local:
            self._local.release()
        else:
            r = _get_redis()
            if r and token:
                self._release_redis(r, token)


_semaphore = _DistributedSemaphore(int(MAX_CONCURRENT_GEMINI))

# Thread-safe model caching
_model = None
_model_lock = threading.Lock()


def _get_model():  # noqa: ANN202 — return type depends on SDK version
    """Get the Gemini model instance (cached, thread-safe)."""
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_API_KEY)
                _model = genai.GenerativeModel("gemini-2.5-flash")
    return _model


# ---------- Retry with jitter + Retry-After ----------

def _call_with_retry(func, max_retries: int = 5):
    """Call a function with exponential backoff + jitter on retryable errors.

    Respects Retry-After header (surfaced via exception message), caps
    backoff at 30s, and adds random jitter to prevent thundering herd.
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            return func()
        except (ConnectionError, TimeoutError, OSError) as e:
            last_exception = e
            wait_time = min(2 ** attempt, 30)
            jitter = random.uniform(0, wait_time * 0.5)
            logger.warning("Retryable connection error, retrying in %.1fs (attempt %d/%d): %s",
                           wait_time + jitter, attempt + 1, max_retries, str(e)[:100])
            time.sleep(wait_time + jitter)
        except Exception as e:
            last_exception = e
            error_str = str(e)
            if any(code in error_str for code in ("429", "500", "502", "503", "504")) or \
                    "rate" in error_str.lower() or "quota" in error_str.lower():
                # Try to parse Retry-After from the error message
                retry_after = _parse_retry_after(error_str)
                wait_time = retry_after if retry_after else min(2 ** attempt, 30)
                jitter = random.uniform(0, wait_time * 0.5)
                logger.warning("Retryable API error, retrying in %.1fs (attempt %d/%d): %s",
                               wait_time + jitter, attempt + 1, max_retries, error_str[:100])
                time.sleep(wait_time + jitter)
            else:
                raise
    raise RuntimeError(f"Failed after {max_retries} retries") from last_exception


def _parse_retry_after(error_str: str) -> float | None:
    """Try to extract a Retry-After value (seconds) from an error string."""
    import re
    match = re.search(r'retry.?after[:\s]*(\d+)', error_str, re.IGNORECASE)
    if match:
        return min(float(match.group(1)), 60)
    return None


def classify_image(image_bytes: bytes, keywords: list[str]) -> dict:
    """Classify an image against a list of keywords using Gemini.

    Returns: {"keyword": str | None, "confidence": float, "description": str}
    """
    if GEMINI_MOCK:
        import random as _rand
        kw = _rand.choice(keywords) if keywords else None
        return {
            "keyword": kw,
            "confidence": round(_rand.uniform(0.7, 0.95), 2),
            "description": f"Mock classification: {kw}",
        }

    keywords_text = "\n".join(f"- {kw}" for kw in keywords)
    prompt = f"""Analyze this image and determine which of the following keywords best describes what is shown. Consider the main subject, activity, context, and any related themes.

Keywords:
{keywords_text}

IMPORTANT: Always pick the BEST matching keyword, even if the match is indirect or partial. Only set keyword to null if the image is completely unrelated (e.g., a logo, icon, or decorative graphic with no connection to any keyword).

Confidence calibration:
- 0.8-1.0: The keyword clearly and directly describes the main subject
- 0.5-0.8: Good match — the keyword relates to the primary activity or setting
- 0.2-0.5: Weak but reasonable match — the keyword is tangentially related
- 0.1-0.2: Very weak — only a loose thematic connection
- Below 0.1: No meaningful connection (set keyword to null)

Respond with ONLY a JSON object:
{{"keyword": "the best matching keyword", "confidence": 0.0-1.0, "description": "brief description of what you see"}}"""

    def _do_classify():
        model = _get_model()

        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes},
        ])

        text = response.text.strip()
        # Strip markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Gemini returned invalid JSON: %s", text[:200])
            return {"keyword": None, "confidence": 0, "description": "Invalid API response"}

        return {
            "keyword": result.get("keyword"),
            "confidence": float(result.get("confidence", 0)),
            "description": result.get("description", ""),
        }

    with _semaphore:
        return _call_with_retry(_do_classify)


def resolve_location(ambiguous_location: str, known_locations: list[str]) -> str:
    """Resolve an ambiguous location to City, State format using Gemini.

    Returns: "City, State" string
    """
    if GEMINI_MOCK:
        return f"{ambiguous_location}, XX"

    locations_text = ", ".join(known_locations) if known_locations else "none"
    prompt = f"""Given these locations associated with a business website, resolve the ambiguous location to its full city, state format.

Known locations from this website: {locations_text}
Ambiguous location to resolve: {ambiguous_location}

Respond with ONLY: "City, State" (e.g., "Springfield, IL")"""

    def _do_resolve():
        model = _get_model()
        response = model.generate_content(prompt)
        return response.text.strip().strip('"')

    with _semaphore:
        return _call_with_retry(_do_resolve)


def detect_location_pages(pages: list[dict]) -> list[dict]:
    """Detect which pages are location-specific using Gemini.

    Args:
        pages: list of {"url": str, "title": str | None, "meta_description": str | None}

    Returns: list of {"url": str, "is_location": bool, "location": str | None}
    """
    if GEMINI_MOCK:
        return [{"url": p["url"], "is_location": False, "location": None} for p in pages]

    if not pages:
        return []

    results = []
    batch_size = 40
    for i in range(0, len(pages), batch_size):
        batch = pages[i:i + batch_size]
        batch_results = _detect_location_batch(batch)
        results.extend(batch_results)

    return results


def _detect_location_batch(pages: list[dict]) -> list[dict]:
    """Process a single batch of pages for location detection."""
    page_lines = []
    for idx, p in enumerate(pages):
        title = p.get("title") or "No title"
        meta = p.get("meta_description") or "No description"
        page_lines.append(f'{idx}. URL: {p["url"]}\n   Title: {title}\n   Description: {meta[:200]}')

    pages_text = "\n".join(page_lines)
    prompt = f"""Analyze these web pages and determine which ones are location/service-area pages for a local business. A location page typically represents a specific city or area where the business operates.

Pages:
{pages_text}

For each page, respond with a JSON array. Each element should have:
- "index": the page number
- "is_location": true if this is a location-specific page
- "location": "City, State" format if it's a location page, null otherwise

Respond with ONLY the JSON array, no other text."""

    def _do_detect():
        model = _get_model()
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Gemini location detection returned invalid JSON: %s", text[:200])
            return [{"url": p["url"], "is_location": False, "location": None} for p in pages]

        result_map = {}
        for item in parsed:
            idx = item.get("index", -1)
            result_map[idx] = item

        results = []
        for idx, p in enumerate(pages):
            if idx in result_map:
                item = result_map[idx]
                results.append({
                    "url": p["url"],
                    "is_location": bool(item.get("is_location")),
                    "location": item.get("location"),
                })
            else:
                results.append({"url": p["url"], "is_location": False, "location": None})

        return results

    with _semaphore:
        return _call_with_retry(_do_detect)


# ---------- Chunked classification to limit memory ----------

def classify_batch(images: list[tuple[int, bytes]], keywords: list[str],
                   progress_callback=None) -> dict[int, dict]:
    """Classify a batch of images concurrently, processing in chunks.

    Instead of submitting all images at once (which holds all resized bytes
    in the futures queue), processes in chunks of MAX_CONCURRENT_GEMINI.

    Args:
        images: list of (image_id, image_bytes)
        keywords: list of keyword strings
        progress_callback: optional callable(current, total) for progress

    Returns: dict mapping image_id to classification result
    """
    results = {}
    total = len(images)
    completed = 0
    chunk_size = int(MAX_CONCURRENT_GEMINI)

    for chunk_start in range(0, total, chunk_size):
        chunk = images[chunk_start:chunk_start + chunk_size]

        with ThreadPoolExecutor(max_workers=chunk_size) as executor:
            futures = {}
            for image_id, image_bytes in chunk:
                future = executor.submit(classify_image, image_bytes, keywords)
                futures[future] = image_id

            for future in as_completed(futures):
                image_id = futures[future]
                completed += 1
                try:
                    results[image_id] = future.result()
                except Exception as e:
                    logger.error("Classification failed for image %d: %s", image_id, e)
                    results[image_id] = {
                        "keyword": None,
                        "confidence": 0,
                        "description": f"Error: {str(e)}",
                    }

                if progress_callback:
                    progress_callback(completed, total)

    return results
