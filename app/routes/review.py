"""Review routes — JSON API for pipeline status and review UI data."""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from celery.result import AsyncResult
from pydantic import BaseModel
from psycopg2.extensions import connection as PgConnection

from app.database import db_dependency
from app import models
from app.config import STALE_TASK_MINUTES
from app.deps import require_project_ownership, serialize_for_json

router = APIRouter()


class ConfirmPayload(BaseModel):
    included_images: list[int]
    overrides: list[dict] = []


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: int,
                      db: PgConnection = Depends(db_dependency)):
    """Return full project detail with images grouped by keyword."""
    project = models.get_project(db, project_id)
    if not project:
        return JSONResponse({"error": "Project not found"}, status_code=404)
    require_project_ownership(project, request.state.session_id)

    project_dict = dict(project)
    keywords = json.loads(project["keywords"])
    all_images = models.get_project_images(db, project_id)

    # Separate by status
    active_images = [dict(img) for img in all_images
                     if img["status"] in ("classified", "confirmed", "pending")]
    auto_skipped = [dict(img) for img in all_images
                    if img["status"] == "auto_skipped"]
    duplicates = [dict(img) for img in all_images
                  if img["status"] == "duplicate"]
    skipped = [dict(img) for img in all_images
               if img["status"] == "skipped"]

    # Group active images by keyword
    by_keyword: dict[str, list[dict]] = defaultdict(list)
    for img in active_images:
        kw = img.get("keyword") or "Unassigned"
        by_keyword[kw].append(img)

    keyword_groups = []
    for kw in keywords:
        if kw in by_keyword:
            keyword_groups.append({"keyword": kw, "images": by_keyword[kw]})
    if "Unassigned" in by_keyword:
        keyword_groups.append({"keyword": "Unassigned", "images": by_keyword["Unassigned"]})

    # Build location list
    all_locations = sorted(set(
        img.get("location") for img in active_images if img.get("location")
    ))
    try:
        project_locations = json.loads(project["locations"] or "[]")
        all_locations = sorted(set(all_locations) | set(project_locations))
    except (json.JSONDecodeError, TypeError):
        pass

    active_count = len([img for img in active_images if img.get("keyword") and img.get("location")])

    return JSONResponse(serialize_for_json({
        "project": project_dict,
        "keyword_groups": keyword_groups,
        "auto_skipped": auto_skipped,
        "duplicates": duplicates,
        "skipped": skipped,
        "keywords": keywords,
        "all_locations": all_locations,
        "active_count": active_count,
    }))


@router.get("/projects/{project_id}/status")
async def pipeline_status(request: Request, project_id: int,
                          db: PgConnection = Depends(db_dependency)):
    """Polling endpoint for multi-stage pipeline progress."""
    project = models.get_project(db, project_id)
    if not project:
        return JSONResponse({"status": "unknown"})
    require_project_ownership(project, request.state.session_id)

    # If project is already in review, signal completion
    if project["status"] in ("review", "crawled", "previewing"):
        return JSONResponse({"status": "complete"})

    if not project["celery_task_id"]:
        return JSONResponse({"status": project["status"]})

    result = AsyncResult(project["celery_task_id"])

    if result.state == "PROGRESS":
        info = result.info or {}
        return JSONResponse({
            "status": "progress",
            "current": info.get("current", 0),
            "total": info.get("total", 0),
            "message": info.get("message", ""),
            "stage": info.get("stage", ""),
            "stage_number": info.get("stage_number"),
            "overall_progress": info.get("overall_progress"),
            "latest_preview": info.get("latest_preview"),
        })
    elif result.state == "SUCCESS":
        return JSONResponse({
            "status": "complete",
            "result": result.result,
        })
    elif result.state == "FAILURE":
        return JSONResponse({
            "status": "failed",
            "error": str(result.result),
        })
    elif result.state == "PENDING" and project["status"] in ("processing", "crawling", "classifying"):
        try:
            created = project["created_at"]
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if datetime.now(tz=timezone.utc) - created > timedelta(minutes=STALE_TASK_MINUTES):
                models.update_project_status(db, project_id, "failed")
                db.commit()
                return JSONResponse({
                    "status": "failed",
                    "error": "Task appears to have been lost. Please create a new project.",
                })
        except (ValueError, TypeError):
            pass
        return JSONResponse({"status": "pending"})
    else:
        return JSONResponse({"status": result.state.lower()})


@router.post("/projects/{project_id}/confirm")
async def confirm_review(request: Request, project_id: int,
                         db: PgConnection = Depends(db_dependency)):
    """Save edits from review page and start generation."""
    project = models.get_project(db, project_id)
    if not project:
        return JSONResponse({"error": "Project not found"}, status_code=404)
    require_project_ownership(project, request.state.session_id)

    # Early guard — reject before any mutations if already generating
    if project["status"] in ("generating", "processing"):
        return JSONResponse(
            {"error": "Generation already in progress"},
            status_code=409,
        )

    try:
        payload = ConfirmPayload(**(await request.json()))
    except Exception:
        return JSONResponse({"error": "Invalid request body"}, status_code=400)
    included_ids = set(payload.included_images)
    project_image_ids = {img["id"] for img in models.get_project_images(db, project_id)}

    # Apply overrides
    for override in payload.overrides:
        img_id = override.get("image_id")
        if not img_id or img_id not in project_image_ids:
            continue
        updates = {}
        if "keyword" in override and override["keyword"]:
            kw = override["keyword"]
            if len(kw) <= 500:
                updates["keyword"] = kw
        if "location" in override and override["location"]:
            loc = override["location"]
            if len(loc) <= 500:
                updates["location"] = loc
        if updates:
            models.update_project_image(db, img_id, **updates)

    # Update all images based on include/exclude
    all_images = models.get_project_images(db, project_id)
    for img in all_images:
        if img["status"] in ("duplicate",):
            continue

        img_id = img["id"]

        if img_id in included_ids:
            if img["status"] in ("auto_skipped", "skipped", "pending"):
                models.update_project_image(db, img_id, status="classified")
        else:
            if img["status"] in ("classified", "confirmed", "pending"):
                models.update_project_image(db, img_id, status="skipped")

    # Atomic status transition BEFORE dispatching Celery task to prevent races
    # NOTE: Image edits above are committed together with the status transition below
    from app.tasks.generate_tasks import generate_overlays

    rows = models.update_project_status_if(
        db, project_id, "generating",
        allowed_statuses=("review", "crawled", "previewing", "failed"),
        celery_task_id="",  # Clear stale task ID to prevent false "complete" status
    )
    db.commit()
    if rows == 0:
        return JSONResponse(
            {"error": "Generation already in progress"},
            status_code=409,
        )

    try:
        task = generate_overlays.delay(project_id)
    except Exception:
        models.update_project_status(db, project_id, "failed")
        db.commit()
        return JSONResponse(
            {"error": "Failed to start generation"},
            status_code=503,
        )

    # Store celery_task_id for progress tracking
    models.update_project_status(db, project_id, "generating", task.id)
    db.commit()

    return JSONResponse({"id": project_id, "status": "generating"})
