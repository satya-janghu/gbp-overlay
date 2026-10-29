"""Preview routes — image serving."""
import logging
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from psycopg2.extensions import connection as PgConnection

from app.config import DATA_DIR
from app.database import db_dependency
from app.deps import require_project_ownership, safe_path
from app import models

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/projects/{project_id}/images/{image_id}/preview")
def serve_preview_image(project_id: int, image_id: int, request: Request,
                        db: PgConnection = Depends(db_dependency)):
    """Serve a preview, overlay, or original image file.

    Fallback chain: preview file → overlay file → original_path → source_url redirect → 404
    """
    project = models.get_project(db, project_id)
    require_project_ownership(project, request.state.session_id)

    # 1. Preview file (generated during pipeline stage 4)
    preview_path = safe_path(DATA_DIR, "processed", str(project_id), f"preview_{image_id}.jpg")
    if os.path.exists(preview_path):
        logger.debug("Serving preview file for image %d: %s", image_id, preview_path)
        return FileResponse(preview_path, media_type="image/jpeg")

    logger.debug("Preview file missing for image %d: %s", image_id, preview_path)

    # 2. Overlay file (used during generation progress)
    overlay_path = safe_path(DATA_DIR, "processed", str(project_id), f"overlay_{image_id}.jpg")
    if os.path.exists(overlay_path):
        logger.debug("Serving overlay file for image %d: %s", image_id, overlay_path)
        return FileResponse(overlay_path, media_type="image/jpeg")

    logger.debug("Overlay file missing for image %d: %s", image_id, overlay_path)

    # 3. Original uploaded image
    try:
        image = models.get_image(db, image_id)
    except Exception:
        logger.exception("DB error looking up image %d", image_id)
        return JSONResponse({"error": "Preview not found"}, status_code=404)
    if image and image["project_id"] == project_id and image.get("original_path"):
        original_path = image["original_path"]
        base = os.path.realpath(DATA_DIR)
        if os.path.realpath(original_path).startswith(base + os.sep) and os.path.exists(original_path):
            logger.debug("Serving original file for image %d: %s", image_id, original_path)
            return FileResponse(original_path, media_type="image/jpeg")
        logger.debug("Original file missing or outside DATA_DIR for image %d: %s (exists=%s)",
                     image_id, original_path, os.path.exists(original_path))

    # 4. Redirect to source_url as last resort
    if image and image.get("source_url"):
        logger.debug("Redirecting to source_url for image %d: %s", image_id, image["source_url"])
        return RedirectResponse(url=image["source_url"], status_code=302)

    logger.warning("No preview available for image %d in project %d", image_id, project_id)
    return JSONResponse({"error": "Preview not found"}, status_code=404)

