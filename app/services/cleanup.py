"""Scheduled cleanup of expired files."""
import os
import logging
from datetime import datetime, timedelta, timezone
from app.config import DATA_DIR, FILE_RETENTION_HOURS
from app.database import get_db, return_db
from app import models

logger = logging.getLogger(__name__)


def cleanup_expired_downloads() -> None:
    """Delete expired ZIP files and update download records."""
    db = get_db()
    try:
        expired = models.get_expired_downloads(db)
        cleaned = 0

        for download in expired:
            zip_path = download["zip_path"]
            file_gone = True  # default: safe to null the path
            if zip_path:
                try:
                    os.remove(zip_path)
                    cleaned += 1
                except FileNotFoundError:
                    pass  # Already deleted by another process
                except OSError as e:
                    logger.error("Failed to delete %s: %s", zip_path, e)
                    file_gone = False  # Don't null — retry next hour

            if file_gone:
                with db.cursor() as cur:
                    cur.execute(
                        "UPDATE downloads SET zip_path = NULL WHERE id = %s",
                        (download["id"],)
                    )

        db.commit()
        if cleaned:
            logger.info("Cleaned up %d expired download(s)", cleaned)
    finally:
        return_db(db)


def cleanup_orphaned_files() -> None:
    """Clean up temp files in uploads/ and processed/ older than retention period."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=int(FILE_RETENTION_HOURS))
    cutoff_ts = cutoff.timestamp()

    for subdir in ["uploads", "processed"]:
        # Note: downloads/ is managed by cleanup_expired_downloads() using DB expiration
        dir_path = os.path.join(DATA_DIR, subdir)
        if not os.path.exists(dir_path):
            continue

        cleaned = 0
        for root, dirs, files in os.walk(dir_path):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    if os.path.getmtime(filepath) < cutoff_ts:
                        os.remove(filepath)
                        cleaned += 1
                except OSError as e:
                    logger.error("Failed to delete orphaned file %s: %s", filepath, e)

        # Remove empty directories
        for root, dirs, files in os.walk(dir_path, topdown=False):
            for d in dirs:
                dirpath = os.path.join(root, d)
                try:
                    if not os.listdir(dirpath):
                        os.rmdir(dirpath)
                except OSError:
                    pass

        if cleaned:
            logger.info("Cleaned %d orphaned file(s) from %s/", cleaned, subdir)


def run_cleanup() -> None:
    """Run all cleanup tasks."""
    logger.info("Running scheduled cleanup...")
    cleanup_expired_downloads()
    cleanup_orphaned_files()
    logger.info("Cleanup complete")
