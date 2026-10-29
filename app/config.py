"""Application configuration loaded from environment variables."""

import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = os.environ.get("DATA_DIR", str(BASE_DIR / "data"))
FONT_DIR = str(Path(__file__).resolve().parent / "static" / "fonts")

# Database
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/gbp_overlay")

# Redis
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Security
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    raise RuntimeError("SECRET_KEY environment variable must be set")
SECRET_KEY = _secret


def ensure_data_dirs():
    """Create data subdirectories. Call from app lifespan, not import time."""
    os.makedirs(os.path.join(DATA_DIR, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "processed"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "downloads"), exist_ok=True)

# Gemini AI
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MOCK = os.environ.get("GEMINI_MOCK", "false").lower() in ("true", "1", "yes")
if not GEMINI_MOCK and not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY must be set when GEMINI_MOCK is not enabled")
MAX_CONCURRENT_GEMINI = int(os.environ.get("MAX_CONCURRENT_GEMINI", "15"))

# Crawling
CRAWL_RATE_LIMIT = float(os.environ.get("CRAWL_RATE_LIMIT", "1.0"))
CRAWL_CONCURRENCY = int(os.environ.get("CRAWL_CONCURRENCY", "5"))

# File retention
FILE_RETENTION_HOURS = int(os.environ.get("FILE_RETENTION_HOURS", "24"))

# Resource limits
MAX_IMAGES_PER_PROJECT = int(os.environ.get("MAX_IMAGES_PER_PROJECT", "500"))
MAX_PAGES_TO_CRAWL = int(os.environ.get("MAX_PAGES_TO_CRAWL", "200"))

# Session
SESSION_COOKIE_MAX_AGE = int(os.environ.get("SESSION_COOKIE_MAX_AGE", "15552000"))

# Task monitoring
STALE_TASK_MINUTES = 30

# Font mapping
FONTS = {
    "Montserrat": {"bold": "Montserrat-Bold.ttf", "regular": "Montserrat-SemiBold.ttf"},
    "Poppins": {"bold": "Poppins-Bold.ttf", "regular": "Poppins-SemiBold.ttf"},
    "Oswald": {"bold": "Oswald-Bold.ttf", "regular": "Oswald-SemiBold.ttf"},
    "Roboto": {"bold": "Roboto-Bold.ttf", "regular": "Roboto-Medium.ttf"},
    "Playfair Display": {"bold": "Playfair-Display-Bold.ttf", "regular": "Playfair-Display-SemiBold.ttf"},
    "Lato": {"bold": "Lato-Bold.ttf", "regular": "Lato-Regular.ttf"},
    "Bebas Neue": {"bold": "BebasNeue-Regular.ttf", "regular": "BebasNeue-Regular.ttf"},
    "Raleway": {"bold": "Raleway-Bold.ttf", "regular": "Raleway-SemiBold.ttf"},
    "Nunito": {"bold": "Nunito-Bold.ttf", "regular": "Nunito-SemiBold.ttf"},
}
