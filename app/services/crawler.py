"""Website crawler for extracting images from business websites."""
import ipaddress
import os
import re
import socket
import time
import threading
import logging
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from lxml import etree
from app.config import CRAWL_RATE_LIMIT, DATA_DIR

logger = logging.getLogger(__name__)

USER_AGENT = "GBP-Overlay-Tool/1.0 (+https://getsatya.com)"
REQUEST_TIMEOUT = 10
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB max download


class DomainRateLimiter:
    """Thread-safe per-domain rate limiter.

    Uses Redis sliding window when available for cross-worker rate limiting.
    Falls back to in-process locking when Redis is unavailable.
    """

    def __init__(self, min_interval: float = CRAWL_RATE_LIMIT):
        self._min_interval = min_interval
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()
        self._redis = None
        self._redis_checked = False

    def _get_redis(self):
        """Lazy-init Redis client for cross-worker rate limiting (double-checked lock)."""
        if not self._redis_checked:
            with self._lock:
                if not self._redis_checked:
                    try:
                        from app.config import REDIS_URL
                        import redis as redis_lib
                        self._redis = redis_lib.Redis.from_url(
                            REDIS_URL, socket_connect_timeout=2, decode_responses=True,
                        )
                        self._redis.ping()
                    except Exception:
                        self._redis = None
                    self._redis_checked = True
        return self._redis

    def wait(self, domain: str) -> None:
        """Block until enough time has passed since the last request to `domain`."""
        r = self._get_redis()
        if r is not None:
            self._wait_redis(r, domain)
        else:
            self._wait_local(domain)

    # Lua script for atomic rate limiting: check + set timestamp in one call
    _RATE_LIMIT_LUA = """\
local last = redis.call('get', KEYS[1])
local now = tonumber(ARGV[1])
local interval = tonumber(ARGV[2])
if last then
    local remaining = interval - (now - tonumber(last))
    if remaining > 0 then return tostring(remaining) end
end
redis.call('set', KEYS[1], tostring(now), 'EX', math.ceil(interval * 10) + 1)
return '0'
"""

    def _wait_redis(self, r, domain: str) -> None:
        """Redis-based atomic rate limiter using Lua script (no TOCTOU race)."""
        key = f"crawl_rate:{domain}"
        while True:
            now = time.time()
            # Redis EVAL runs Lua atomically — no TOCTOU between check and set
            result = r.eval(  # noqa: S307 — Redis EVAL command, not Python eval
                self._RATE_LIMIT_LUA, 1, key,
                now, self._min_interval,
            )
            remaining = float(result)
            if remaining <= 0:
                break
            time.sleep(remaining)

    def _wait_local(self, domain: str) -> None:
        """In-process fallback rate limiter."""
        with self._lock:
            now = time.monotonic()
            last = self._last_request.get(domain, 0.0)
            remaining = self._min_interval - (now - last)
            if remaining > 0:
                self._last_request[domain] = now + remaining
            else:
                self._last_request[domain] = now
                remaining = 0.0

        if remaining > 0:
            time.sleep(remaining)


def _make_session() -> requests.Session:
    """Create a requests.Session with the standard User-Agent pre-set."""
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _assert_safe_url(url: str, allowed_domain: str | None = None):
    """Validate URL is safe to fetch (no SSRF to internal networks).

    Raises ValueError on unsafe URLs.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    if allowed_domain and hostname != allowed_domain:
        raise ValueError(f"URL domain {hostname} does not match allowed domain {allowed_domain}")

    # Resolve hostname and check for private/loopback IPs
    try:
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                raise ValueError(f"URL resolves to non-public IP: {addr}")
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname}")

# Location page URL patterns
LOCATION_PATTERNS = [
    r'/locations?/',
    r'/service-areas?/',
    r'/areas-we-serve/',
    r'/cities/',
    r'/regions/',
    r'/branches/',
    r'/offices/',
]


def _check_robots(base_url: str) -> RobotFileParser:
    """Parse robots.txt for the domain."""
    rp = RobotFileParser()
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        rp.set_url(robots_url)
        rp.read()
    except (ConnectionError, TimeoutError, OSError, ValueError):
        pass  # If robots.txt is unavailable, allow all
    return rp


def _is_location_page(url: str) -> bool:
    """Check if URL matches common location page patterns."""
    path = urlparse(url).path.lower()
    return any(re.search(pattern, path) for pattern in LOCATION_PATTERNS)


_NON_LOCATION_SLUGS = frozenset({
    "about", "about-us", "contact", "contact-us", "services", "pricing",
    "blog", "news", "faq", "faqs", "gallery", "portfolio", "team",
    "careers", "jobs", "privacy", "privacy-policy", "terms",
    "terms-of-service", "sitemap", "home", "index", "login", "signup",
    "register", "dashboard", "admin", "reviews", "testimonials",
    "partners", "resources", "support", "help", "404", "search",
})


def _extract_location_from_url(url: str) -> str | None:
    """Try to extract a location name from the URL slug.

    Only extracts from segments that follow a known location indicator
    (e.g. /locations/springfield-il). Does NOT fall back to the last
    segment, which produces false positives like 'Pricing' or 'Gallery'.
    """
    path = urlparse(url).path.strip("/")
    segments = [s.lower() for s in path.split("/")]

    location_indicators = {"locations", "location", "service-area", "service-areas",
                           "areas-we-serve", "cities", "city", "regions",
                           "branches", "offices"}

    for i, segment in enumerate(segments):
        if segment in location_indicators and i + 1 < len(segments):
            slug = segments[i + 1]
            if slug and len(slug) > 2 and slug not in _NON_LOCATION_SLUGS:
                return slug.replace("-", " ").replace("_", " ").title()

    return None


def fetch_sitemap(website_url: str) -> list[dict]:
    """Fetch and parse sitemap.xml, returning list of page URLs.

    Returns list of dicts: [{"url": "...", "images": [...]}]
    Each entry may have image URLs from <image:image> tags.
    """
    base_url = f"{urlparse(website_url).scheme}://{urlparse(website_url).netloc}"
    sitemap_url = urljoin(base_url, "/sitemap.xml")

    headers = {"User-Agent": USER_AGENT}
    pages = []

    try:
        _assert_safe_url(sitemap_url)
        resp = requests.get(sitemap_url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Failed to fetch sitemap: %s", e)
        return pages

    try:
        root = etree.fromstring(resp.content)
    except Exception as e:
        logger.warning("Failed to parse sitemap XML: %s", e)
        return pages

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
          "image": "http://www.google.com/schemas/sitemap-image/1.1"}

    base_domain = urlparse(website_url).hostname

    # Check if this is a sitemap index
    sitemaps = root.findall(".//sm:sitemap/sm:loc", ns)
    if sitemaps:
        # Recursively fetch child sitemaps
        for loc in sitemaps:
            child_url = loc.text.strip()
            try:
                _assert_safe_url(child_url, allowed_domain=base_domain)
                child_resp = requests.get(child_url, headers=headers, timeout=REQUEST_TIMEOUT)
                child_resp.raise_for_status()
                child_root = etree.fromstring(child_resp.content)
                pages.extend(_parse_sitemap_urls(child_root, ns))
                time.sleep(CRAWL_RATE_LIMIT)
            except Exception as e:
                logger.warning("Failed to fetch child sitemap %s: %s", child_url, e)
    else:
        pages = _parse_sitemap_urls(root, ns)

    return pages


def _parse_sitemap_urls(root, ns: dict) -> list[dict]:
    """Parse URL entries from a sitemap XML root."""
    pages = []
    urls = root.findall(".//sm:url", ns)
    for url_elem in urls:
        loc = url_elem.find("sm:loc", ns)
        if loc is None or not loc.text:
            continue

        page_url = loc.text.strip()

        # Extract image URLs if present
        image_urls = []
        image_elems = url_elem.findall(".//image:image/image:loc", ns)
        for img_elem in image_elems:
            if img_elem.text:
                image_urls.append(img_elem.text.strip())

        pages.append({
            "url": page_url,
            "images": image_urls,
            "is_location": _is_location_page(page_url),
            "location": _extract_location_from_url(page_url),
        })

    return pages


def crawl_page_for_images(page_url: str, js_rendered: bool = False,
                          robot_parser: RobotFileParser | None = None,
                          session: requests.Session | None = None) -> dict:
    """Crawl a single page and extract image URLs plus page metadata.

    Returns dict with keys:
        - image_urls: list of absolute image URLs
        - title: page title or None
        - meta_description: meta description or None
    If robot_parser is provided, checks robots.txt before fetching.
    """
    empty_result = {"image_urls": [], "title": None, "meta_description": None}

    if robot_parser and not robot_parser.can_fetch(USER_AGENT, page_url):
        logger.info("Skipping %s (disallowed by robots.txt)", page_url)
        return empty_result

    if js_rendered:
        return _crawl_with_playwright(page_url)

    http = session or requests
    headers = {} if session else {"User-Agent": USER_AGENT}

    try:
        _assert_safe_url(page_url)
        resp = http.get(page_url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Failed to crawl %s: %s", page_url, e)
        return empty_result

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract page metadata
    title = None
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    meta_description = None
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag and meta_tag.get("content"):
        meta_description = meta_tag["content"].strip()

    image_urls = set()

    # Extract from <img> tags
    for img in soup.find_all("img"):
        src = img.get("src")
        if src:
            image_urls.add(urljoin(page_url, src))

        # Handle srcset
        srcset = img.get("srcset")
        if srcset:
            for entry in srcset.split(","):
                parts = entry.strip().split()
                if parts:
                    image_urls.add(urljoin(page_url, parts[0]))

    # Extract CSS background-image
    for elem in soup.find_all(style=True):
        style = elem["style"]
        bg_matches = re.findall(r'background-image:\s*url\(["\']?([^"\')\s]+)["\']?\)', style)
        for url in bg_matches:
            image_urls.add(urljoin(page_url, url))

    # Filter to likely image URLs
    image_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    filtered = []
    for url in image_urls:
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        if any(path_lower.endswith(ext) for ext in image_extensions) or \
           'image' in path_lower or 'photo' in path_lower or 'media' in path_lower or \
           'wp-content/uploads' in path_lower:
            filtered.append(url)

    return {"image_urls": filtered, "title": title, "meta_description": meta_description}


# Persistent browser context — reuse one Chromium instance across pages
_playwright_ctx = None
_playwright_lock = threading.Lock()
_PLAYWRIGHT_MAX_CONCURRENT_PAGES = 2  # Limit concurrent pages to cap RAM


def _get_playwright_browser():
    """Return a persistent Playwright browser instance (lazy, thread-safe).

    Returns (playwright_instance, browser) or (None, None) on failure.
    """
    global _playwright_ctx
    if _playwright_ctx is None:
        with _playwright_lock:
            if _playwright_ctx is None:
                try:
                    from playwright.sync_api import sync_playwright
                    pw = sync_playwright().start()
                    browser = pw.chromium.launch(headless=True)
                    _playwright_ctx = (pw, browser)
                except ImportError:
                    logger.warning("Playwright not installed")
                    _playwright_ctx = (None, None)
                except Exception as e:
                    logger.warning("Failed to launch Playwright browser: %s", e)
                    _playwright_ctx = (None, None)
    return _playwright_ctx


_playwright_page_semaphore = threading.Semaphore(_PLAYWRIGHT_MAX_CONCURRENT_PAGES)


def _crawl_with_playwright(page_url: str) -> dict:
    """Crawl a page using Playwright for JS-rendered content.

    Reuses a persistent browser context and creates new pages (not browsers)
    per URL. Limits concurrent pages to cap memory usage.

    Returns dict with image_urls, title, meta_description.
    """
    empty_result = {"image_urls": [], "title": None, "meta_description": None}

    try:
        _assert_safe_url(page_url)
    except ValueError as e:
        logger.warning("Skipping unsafe URL %s: %s", page_url, e)
        return empty_result

    pw, browser = _get_playwright_browser()
    if browser is None:
        return empty_result

    _playwright_page_semaphore.acquire()
    try:
        page = browser.new_page(user_agent=USER_AGENT)
        try:
            page.goto(page_url, wait_until="networkidle", timeout=15000)

            title = page.title()

            meta = page.query_selector('meta[name="description"]')
            meta_description = meta.get_attribute("content") if meta else None

            image_urls = []
            images = page.query_selector_all("img")
            for img in images:
                src = img.get_attribute("src")
                if src:
                    image_urls.append(urljoin(page_url, src))

            return {"image_urls": image_urls, "title": title, "meta_description": meta_description}
        finally:
            page.close()
    except Exception as e:
        logger.warning("Playwright crawl failed for %s: %s", page_url, e)
        return empty_result
    finally:
        _playwright_page_semaphore.release()


def crawl_page_batch(
    page: dict,
    images_per_page: int,
    js_rendered: bool,
    robot_parser: RobotFileParser | None,
    rate_limiter: DomainRateLimiter,
    session: requests.Session | None = None,
) -> dict:
    """Crawl a single page and download qualifying images (thread-safe, no DB writes).

    Returns a dict with:
        - page_url: str
        - page_title: str | None
        - page_meta: str | None
        - url_location: str | None
        - url_is_location: bool
        - downloaded: list of dicts with keys: img_url, img_data, width, height, img_hash
    """
    from app.services import image_processor

    page_url = page["url"]
    domain = urlparse(page_url).hostname or ""

    # Rate-limit before the page request
    rate_limiter.wait(domain)

    image_urls = page.get("images", [])
    page_title = None
    page_meta = None

    if not image_urls:
        crawl_result = crawl_page_for_images(
            page_url, js_rendered, robot_parser=robot_parser, session=session
        )
        image_urls = crawl_result["image_urls"]
        page_title = crawl_result["title"]
        page_meta = crawl_result["meta_description"]

    downloaded = []
    for img_url in image_urls:
        if len(downloaded) >= images_per_page:
            break

        # Rate-limit image downloads to the same domain
        img_domain = urlparse(img_url).hostname or ""
        if img_domain == domain:
            rate_limiter.wait(domain)

        img_data, width, height = download_image(img_url, session=session)
        if img_data is None or width < 720:
            continue

        img_hash = image_processor.compute_hash(img_data)
        downloaded.append({
            "img_url": img_url,
            "img_data": img_data,
            "width": width,
            "height": height,
            "img_hash": img_hash,
        })

    return {
        "page_url": page_url,
        "page_title": page_title,
        "page_meta": page_meta,
        "url_location": page.get("location"),
        "url_is_location": page.get("is_location", False),
        "downloaded": downloaded,
    }


def download_image(url: str, session: requests.Session | None = None) -> tuple[bytes | None, int, int]:
    """Download an image and return (bytes, width, height) or (None, 0, 0) on failure."""
    http = session or requests
    headers = {} if session else {"User-Agent": USER_AGENT}
    try:
        _assert_safe_url(url)
        resp = http.get(url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
        resp.raise_for_status()

        # Check content type
        content_type = resp.headers.get("content-type", "")
        if not any(t in content_type for t in ["image/", "octet-stream"]):
            return None, 0, 0

        # Check Content-Length header before downloading
        content_length = resp.headers.get("content-length")
        if content_length and int(content_length) > MAX_IMAGE_SIZE:
            logger.debug("Image too large (%s bytes): %s", content_length, url)
            return None, 0, 0

        # Stream download with size limit
        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=8192):
            total += len(chunk)
            if total > MAX_IMAGE_SIZE:
                logger.debug("Image exceeded size limit during download: %s", url)
                return None, 0, 0
            chunks.append(chunk)
        data = b"".join(chunks)

        from PIL import Image as PILImage
        import io
        img = PILImage.open(io.BytesIO(data))
        return data, img.size[0], img.size[1]
    except Exception as e:
        logger.debug("Failed to download %s: %s", url, e)
        return None, 0, 0
