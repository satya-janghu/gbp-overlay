"""ZIP file builder with manifest CSV."""
import logging
import os
import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone
from slugify import slugify
from app.config import DATA_DIR, FILE_RETENTION_HOURS
from app import models

logger = logging.getLogger(__name__)

def start_zip_in_memory() -> tuple[io.BytesIO, zipfile.ZipFile, list, dict]:
    """Open a new in-memory ZIP for progressive writing.

    Returns (zip_buffer, zip_file, manifest_rows, filename_counts).
    """
    zip_buffer = io.BytesIO()
    zf = zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED)
    return zip_buffer, zf, [], {}


def add_image_to_zip(
    zf: zipfile.ZipFile,
    manifest_rows: list,
    filename_counts: dict,
    jpeg_bytes: bytes,
    keyword: str,
    location: str,
    source_url: str = "",
    overlay_position: str = "",
) -> None:
    """Write a single JPEG into the open ZIP file."""
    location_slug = slugify(location or "unknown")
    keyword_slug = slugify(keyword or "unknown")
    base_name = f"{location_slug}-{keyword_slug}"

    if base_name not in filename_counts:
        filename_counts[base_name] = 0
    filename_counts[base_name] += 1

    if filename_counts[base_name] > 1:
        filename = f"{base_name}-{filename_counts[base_name]}.jpg"
    else:
        filename = f"{base_name}.jpg"

    zf.writestr(filename, jpeg_bytes)

    manifest_rows.append({
        "filename": filename,
        "location": location or "",
        "keyword": keyword or "",
        "source_url": source_url,
        "overlay_position": overlay_position,
    })


def finalize_zip_in_memory(
    zip_buffer: io.BytesIO,
    zf: zipfile.ZipFile,
    manifest_rows: list,
    project_id: int,
    db,
) -> str:
    """Write manifest CSV, close ZIP, and write to disk.

    Args:
        db: Active database connection from the caller (avoids orphan connections).

    Returns:
        The absolute path to the written ZIP file on disk.
    """
    # Write manifest CSV into the ZIP
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=["filename", "location", "keyword", "source_url", "overlay_position"],
    )
    writer.writeheader()
    writer.writerows(manifest_rows)
    zf.writestr("manifest.csv", csv_buffer.getvalue())
    zf.close()

    zip_bytes = zip_buffer.getvalue()
    zip_size = len(zip_bytes)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=FILE_RETENTION_HOURS)

    project = models.get_project(db, project_id)

    client_slug = slugify(project["client_name"] or "project")
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    zip_filename = f"{client_slug}-gbp-images-{timestamp}.zip"
    zip_path = os.path.join(DATA_DIR, "downloads", zip_filename)

    # Write to disk — required (web and worker share the same volume)
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with open(zip_path, "wb") as f:
        f.write(zip_bytes)
    logger.info("ZIP written to disk: %s (%d bytes)", zip_path, zip_size)

    models.create_download(
        db=db,
        project_id=project_id,
        session_id=project["session_id"],
        client_name=project["client_name"],
        image_count=len(manifest_rows),
        zip_path=zip_path,
        zip_size=zip_size,
        expires_at=expires_at.isoformat(),
    )
    db.commit()

    # Release the BytesIO backing store now that bytes are persisted
    zip_buffer.close()

    return zip_path
