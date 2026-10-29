"""Project setup and creation routes — JSON API."""
import logging
import os
import json
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from psycopg2.extensions import connection as PgConnection

from app.database import db_dependency
from app import models
from app.config import DATA_DIR, FONTS
from app.services import image_processor
from app.limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/projects")
@limiter.limit("10/minute")
async def create_project(
    request: Request,
    client_name: str = Form(""),
    website_url: str = Form(""),
    keywords: str = Form(...),
    locations: str = Form(""),
    font: str = Form("Montserrat"),
    images_per_page: int = Form(1),  # clamped to 1-50 below
    fetch_anywhere: str = Form("false"),
    js_rendered: str = Form("false"),
    files: list[UploadFile] = File(default=[]),
    db: PgConnection = Depends(db_dependency),
):
    """Create a new project and start the unified pipeline.

    Note: This route is async because it uses UploadFile.read() which is
    an async operation. All DB calls use psycopg2 (synchronous) but are
    fast enough for single-row operations. File I/O is minimal (writing
    uploaded files). For the heavy lifting, we delegate to Celery.
    """
    session_id = request.state.session_id
    images_per_page = max(1, min(images_per_page, 50))

    # Parse string booleans from FormData
    fetch_anywhere_bool = fetch_anywhere.lower() in ("true", "1", "on")
    js_rendered_bool = js_rendered.lower() in ("true", "1", "on")

    # Validate font
    if font not in FONTS:
        return JSONResponse({"error": f"Invalid font: {font}"}, status_code=400)

    # Parse keywords and locations
    keywords_list = [k.strip() for k in keywords.strip().split("\n") if k.strip()]
    locations_list = [loc.strip() for loc in locations.strip().split("\n") if loc.strip()] if locations.strip() else []

    if not keywords_list:
        return JSONResponse(
            {"error": "Please enter at least one keyword."},
            status_code=400,
        )

    try:
        # Create project
        project_id = models.create_project(
            db, session_id,
            client_name=client_name or None,
            website_url=website_url or None,
            keywords_json=json.dumps(keywords_list),
            locations_json=json.dumps(locations_list) if locations_list else None,
            font=font,
            images_per_page=images_per_page,
            fetch_anywhere=fetch_anywhere_bool,
            js_rendered=js_rendered_bool,
        )
        db.commit()

        # Handle uploaded files
        has_uploads = files and files[0].filename
        if has_uploads:
            upload_dir = os.path.join(DATA_DIR, "uploads", str(project_id))
            os.makedirs(upload_dir, exist_ok=True)

            for i, file in enumerate(files):
                if not file.filename:
                    continue

                file_bytes = await file.read()
                is_valid, _error, width, height = image_processor.validate_image(file_bytes)

                if not is_valid:
                    continue

                img_hash = image_processor.compute_hash(file_bytes)
                jpeg_data = image_processor.convert_to_jpeg(file_bytes)
                filename = f"upload_{i+1}.jpg"
                filepath = os.path.join(upload_dir, filename)
                with open(filepath, "wb") as f:
                    f.write(jpeg_data)

                location = locations_list[i % len(locations_list)] if locations_list else ""

                models.add_project_image(
                    db, project_id,
                    original_path=filepath,
                    image_hash=img_hash,
                    status="pending",
                    width=width,
                    height=height,
                    location=location,
                )

            db.commit()  # single commit for all uploaded images

            # Dedup uploaded images
            images = models.get_project_images(db, project_id)
            hashes = {img["id"]: img["image_hash"] for img in images if img["image_hash"]}
            duplicates = image_processor.find_duplicates(hashes)
            for dup_id in duplicates:
                models.update_project_image(db, dup_id, status="duplicate")
            db.commit()

        # Start unified pipeline
        if website_url and website_url.strip():
            from app.tasks.crawl_tasks import process_pipeline
            try:
                task = process_pipeline.delay(project_id)
            except Exception as exc:
                logger.error("Failed to enqueue pipeline task: %s", exc)
                models.update_project_status(db, project_id, "failed")
                db.commit()
                return JSONResponse(
                    {"error": "Background task system unavailable. Please try again shortly."},
                    status_code=503,
                )
            models.update_project_status(db, project_id, "processing", task.id)
            db.commit()
            return JSONResponse({"id": project_id, "status": "processing"})

        elif has_uploads:
            # Upload-only: run pipeline with skip_crawl=True
            from app.tasks.crawl_tasks import process_pipeline
            try:
                task = process_pipeline.delay(project_id, skip_crawl=True)
            except Exception as exc:
                logger.error("Failed to enqueue pipeline task: %s", exc)
                models.update_project_status(db, project_id, "failed")
                db.commit()
                return JSONResponse(
                    {"error": "Background task system unavailable. Please try again shortly."},
                    status_code=503,
                )
            models.update_project_status(db, project_id, "processing", task.id)
            db.commit()
            return JSONResponse({"id": project_id, "status": "processing"})

        else:
            return JSONResponse(
                {"error": "Please provide a website URL or upload images."},
                status_code=400,
            )

    except Exception as exc:
        logger.exception("Unexpected error creating project: %s", exc)
        return JSONResponse(
            {"error": "An unexpected error occurred. Please try again."},
            status_code=500,
        )
