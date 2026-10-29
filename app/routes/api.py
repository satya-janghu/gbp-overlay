"""Internal API endpoints — JSON responses."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from psycopg2.extensions import connection as PgConnection

from app.database import db_dependency
from app import models
from app.deps import require_project_ownership

router = APIRouter()


class KeywordUpdate(BaseModel):
    keyword: str


class LocationUpdate(BaseModel):
    location: str


class StatusUpdate(BaseModel):
    status: str


@router.patch("/images/{image_id}/keyword")
async def update_image_keyword(
    request: Request, image_id: int,
    db: PgConnection = Depends(db_dependency),
):
    """Update keyword assignment for an image."""
    try:
        body = KeywordUpdate(**(await request.json()))
    except Exception:
        return JSONResponse({"error": "Invalid request body"}, status_code=400)
    if len(body.keyword) > 500:
        return JSONResponse({"error": "Keyword too long"}, status_code=400)
    img = models.get_image(db, image_id)
    if not img:
        return JSONResponse({"error": "Not found"}, status_code=404)
    project = models.get_project(db, img["project_id"])
    require_project_ownership(project, request.state.session_id)
    models.update_project_image(db, image_id, keyword=body.keyword)
    db.commit()
    return JSONResponse({"id": image_id, "keyword": body.keyword})


@router.patch("/images/{image_id}/location")
async def update_image_location(
    request: Request, image_id: int,
    db: PgConnection = Depends(db_dependency),
):
    """Update location for an image."""
    try:
        body = LocationUpdate(**(await request.json()))
    except Exception:
        return JSONResponse({"error": "Invalid request body"}, status_code=400)
    if len(body.location) > 500:
        return JSONResponse({"error": "Location too long"}, status_code=400)
    img = models.get_image(db, image_id)
    if not img:
        return JSONResponse({"error": "Not found"}, status_code=404)
    project = models.get_project(db, img["project_id"])
    require_project_ownership(project, request.state.session_id)
    models.update_project_image(db, image_id, location=body.location)
    db.commit()
    return JSONResponse({"id": image_id, "location": body.location})


@router.patch("/images/{image_id}/status")
async def update_image_status(
    request: Request, image_id: int,
    db: PgConnection = Depends(db_dependency),
):
    """Toggle image selection status."""
    try:
        body = StatusUpdate(**(await request.json()))
    except Exception:
        return JSONResponse({"error": "Invalid request body"}, status_code=400)
    allowed_statuses = {"classified", "confirmed", "pending", "skipped", "auto_skipped"}
    if body.status not in allowed_statuses:
        return JSONResponse({"error": "Invalid status"}, status_code=400)
    img = models.get_image(db, image_id)
    if not img:
        return JSONResponse({"error": "Not found"}, status_code=404)
    project = models.get_project(db, img["project_id"])
    require_project_ownership(project, request.state.session_id)
    models.update_project_image(db, image_id, status=body.status)
    db.commit()
    return JSONResponse({"id": image_id, "status": body.status})


@router.patch("/images/{image_id}/restore")
async def restore_image(
    request: Request, image_id: int,
    db: PgConnection = Depends(db_dependency),
):
    """Restore an auto-skipped image back to classified status."""
    img = models.get_image(db, image_id)
    if not img:
        return JSONResponse({"error": "Not found"}, status_code=404)
    project = models.get_project(db, img["project_id"])
    require_project_ownership(project, request.state.session_id)
    models.update_project_image(db, image_id, status="classified")
    db.commit()
    return JSONResponse({"id": image_id, "status": "classified"})
