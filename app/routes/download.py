"""Download and projects routes — JSON API."""
import logging
import os
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, FileResponse
from psycopg2.extensions import connection as PgConnection

from app.database import db_dependency
from app import models
from app.config import DATA_DIR
from app.deps import safe_path, serialize_for_json

logger = logging.getLogger(__name__)

router = APIRouter()

# Status-to-URL mapping for resume links (SPA routes)
_STATUS_URLS = {
    "setup": "/",
    "processing": "/project/{id}/review",
    "crawling": "/project/{id}/review",
    "crawled": "/project/{id}/review",
    "classifying": "/project/{id}/review",
    "matching": "/project/{id}/review",
    "review": "/project/{id}/review",
    "previewing": "/project/{id}/review",
    "generating": "/project/{id}/progress",
    "complete": "/project/{id}/progress",
}

_ACTIVE_STATUSES = {"processing", "crawling", "crawled", "classifying", "matching", "review", "previewing", "generating"}

# Sync def so FastAPI runs it in a threadpool,
# avoiding event loop blocking from synchronous DB reads and file I/O.


@router.get("/projects/{project_id}/download")
def download_zip(request: Request, project_id: int,
                 db: PgConnection = Depends(db_dependency)):
    """Download the generated ZIP file."""
    session_id = request.state.session_id

    try:
        download = models.get_download_for_project(db, session_id, project_id)
        if not download:
            logger.warning("Download not found: project=%d session=%s", project_id, session_id)
            return JSONResponse({"error": "Download not found or expired"}, status_code=404)

        if not download.get("zip_path"):
            logger.warning("No zip_path recorded for project=%d", project_id)
            return JSONResponse({"error": "Download file not found or expired"}, status_code=404)

        try:
            zip_path = safe_path(DATA_DIR, os.path.relpath(download["zip_path"], DATA_DIR))
        except (ValueError, TypeError) as e:
            logger.warning("Invalid zip_path for project=%d: %s", project_id, e)
            return JSONResponse({"error": "Download file not found or expired"}, status_code=404)

        if not os.path.exists(zip_path):
            logger.error("ZIP missing on disk for project=%d: %s", project_id, zip_path)
            return JSONResponse({"error": "Download file not found. It may have expired."}, status_code=404)

        filename = os.path.basename(zip_path)
        logger.info("Serving ZIP from disk: %s", zip_path)
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=filename,
        )

    except Exception as e:
        logger.error("Download error for project=%d: %s", project_id, e)
        return JSONResponse(
            {"error": "Download failed. Please try again."},
            status_code=500,
        )


# Sync def — only does synchronous DB reads.
@router.get("/projects")
def projects_list(request: Request,
                  db: PgConnection = Depends(db_dependency)):
    """Return projects dashboard data for the current session."""
    session_id = request.state.session_id
    projects = models.get_session_projects(db, session_id)
    downloads = models.get_session_downloads(db, session_id)

    # Index downloads by project_id
    dl_by_project: dict[int, dict] = {}
    for d in downloads:
        pid = d["project_id"]
        if pid not in dl_by_project:
            dl_by_project[pid] = serialize_for_json(dict(d))

    active_projects = []
    completed_projects = []
    failed_projects = []

    for p in projects:
        p = dict(p)
        status = p.get("status", "setup")

        # Add resume URL
        url_template = _STATUS_URLS.get(status, "/")
        p["resume_url"] = url_template.replace("{id}", str(p["id"]))

        p = serialize_for_json(p)

        if status in _ACTIVE_STATUSES:
            active_projects.append(p)
        elif status == "complete":
            dl = dl_by_project.get(p["id"])
            if dl:
                p["image_count"] = dl.get("image_count")
                p["zip_size"] = dl.get("zip_size")
                p["has_download"] = True
            else:
                p["image_count"] = None
                p["zip_size"] = None
                p["has_download"] = False
            completed_projects.append(p)
        elif status == "failed":
            failed_projects.append(p)
        elif status == "setup":
            active_projects.append(p)

    return JSONResponse({
        "active": active_projects,
        "completed": completed_projects,
        "failed": failed_projects,
    })
