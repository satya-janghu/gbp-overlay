"""Batch generation and progress routes — JSON API."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from celery.result import AsyncResult
from psycopg2.extensions import connection as PgConnection

from app.database import db_dependency
from app import models
from app.config import STALE_TASK_MINUTES
from app.deps import require_project_ownership

router = APIRouter()


@router.post("/projects/{project_id}/generate")
async def start_generation(request: Request, project_id: int,
                           db: PgConnection = Depends(db_dependency)):
    """Start batch overlay generation."""
    project = models.get_project(db, project_id)
    if not project:
        return JSONResponse({"error": "Project not found"}, status_code=404)
    require_project_ownership(project, request.state.session_id)

    from app.tasks.generate_tasks import generate_overlays

    # Clear stale task ID first to prevent race where old SUCCESS is read
    models.update_project_status(db, project_id, "generating", celery_task_id="")
    db.commit()

    task = generate_overlays.delay(project_id)

    models.update_project_status(db, project_id, "generating", task.id)
    db.commit()

    return JSONResponse({"id": project_id, "status": "generating"})


@router.get("/projects/{project_id}/generation-status")
async def generation_status(request: Request, project_id: int,
                            db: PgConnection = Depends(db_dependency)):
    """Polling endpoint for generation progress."""
    project = models.get_project(db, project_id)
    if not project:
        return JSONResponse({"status": "unknown"})
    require_project_ownership(project, request.state.session_id)

    if project["status"] == "complete":
        return JSONResponse({"status": "complete", "project_id": project_id})

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
        task_result = result.result or {}
        if isinstance(task_result, dict) and task_result.get("error"):
            return JSONResponse({"status": "failed", "error": task_result["error"]})
        return JSONResponse({
            "status": "complete",
            "current": task_result.get("succeeded", 0),
            "total": task_result.get("total", 0),
            "result": task_result,
        })
    elif result.state == "FAILURE":
        return JSONResponse({"status": "failed", "error": str(result.result)})
    elif result.state == "PENDING" and project["status"] in ("generating",):
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
