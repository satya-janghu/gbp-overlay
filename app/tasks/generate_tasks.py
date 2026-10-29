"""Async overlay generation tasks."""
import logging
import os
import requests
from celery import shared_task
from app.database import get_db, return_db
from app import models
from app.services import overlay_renderer, zip_builder

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="generate_overlays")
def generate_overlays(self, project_id: int):
    """Generate overlays for all matched images and build ZIP (fully in-memory)."""
    db = get_db()
    written_zip_path = None
    try:
        project = models.get_project(db, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        models.update_project_status(db, project_id, "generating", self.request.id)
        db.commit()

        font_name = project["font"] or "Montserrat"

        # Get all images ready for overlay (classified or manually assigned)
        images = [img for img in models.get_project_images(db, project_id)
                  if img["status"] in ("classified", "confirmed", "pending") and img["keyword"] and img["location"]]

        if not images:
            # Diagnose the reason
            all_imgs = models.get_project_images(db, project_id)
            has_keywords = any(img["keyword"] for img in all_imgs)
            has_locations = any(img["location"] for img in all_imgs)

            if not all_imgs or all(img["status"] in ("duplicate", "skipped") for img in all_imgs):
                reason = "No images available. Try a different website or upload images manually."
            elif not has_keywords:
                reason = "No images were matched to keywords. Check Gemini API connectivity."
            elif not has_locations:
                reason = "No locations assigned to images. Add locations in the crawl results page."
            else:
                reason = "No images have both keyword and location assigned."

            models.update_project_status(db, project_id, "failed")
            db.commit()
            return {"project_id": project_id, "error": reason}

        total = len(images)
        succeeded = 0
        failed = 0

        # Open ZIP progressively — each JPEG is written immediately
        zip_buffer, zf, manifest_rows, filename_counts = zip_builder.start_zip_in_memory()

        for i, img in enumerate(images):
            self.update_state(state="PROGRESS", meta={
                "stage": "generating",
                "message": f"Generating overlay {i+1}/{total}...",
                "current": i + 1, "total": total,
                "succeeded": succeeded, "failed": failed,
                "latest_preview": None,
            })

            try:
                # Download image bytes from source URL
                image_bytes = None
                original_path = img.get("original_path")
                if original_path and os.path.exists(original_path):
                    with open(original_path, "rb") as f:
                        image_bytes = f.read()
                elif img.get("source_url"):
                    resp = requests.get(img["source_url"], timeout=15)
                    resp.raise_for_status()
                    image_bytes = resp.content
                else:
                    raise ValueError(f"No source for image {img['id']}")

                # Render overlay entirely in memory
                jpeg_bytes = overlay_renderer.render_overlay_bytes(
                    image_bytes=image_bytes,
                    keyword=img["keyword"],
                    location=img["location"],
                    font_name=font_name,
                    position=img.get("overlay_position"),
                )

                # Stream directly into ZIP
                zip_builder.add_image_to_zip(
                    zf, manifest_rows, filename_counts,
                    jpeg_bytes=jpeg_bytes,
                    keyword=img["keyword"],
                    location=img["location"],
                    source_url=img.get("source_url") or "",
                    overlay_position=img.get("overlay_position") or "",
                )

                models.update_project_image(
                    db, img["id"],
                    status="overlaid",
                )
                succeeded += 1

            except Exception as e:
                logger.error("Overlay failed for image %d: %s", img["id"], e)
                models.update_project_image(db, img["id"], status="skipped")
                failed += 1

            db.commit()

        # Guard against empty ZIP
        if succeeded == 0:
            zf.close()
            models.update_project_status(db, project_id, "failed")
            db.commit()
            return {"project_id": project_id, "error": f"All {total} images failed to render."}

        # Finalize ZIP and store in DB
        self.update_state(state="PROGRESS", meta={
            "stage": "zipping",
            "message": "Building ZIP file...",
            "current": total, "total": total,
            "succeeded": succeeded, "failed": failed,
        })

        written_zip_path = zip_builder.finalize_zip_in_memory(zip_buffer, zf, manifest_rows, project_id, db)

        models.update_project_status(db, project_id, "complete")
        db.commit()

        return {
            "project_id": project_id,
            "succeeded": succeeded,
            "failed": failed,
            "total": total,
        }

    except Exception as e:
        logger.error("Generation failed for project %d: %s", project_id, e)
        if written_zip_path:
            try:
                os.remove(written_zip_path)
            except OSError:
                pass  # Orphan cleanup will catch it
        try:
            db.rollback()
            models.update_project_status(db, project_id, "failed")
            db.commit()
        except Exception:
            logger.error("Failed to update project status to 'failed'")
        raise
    finally:
        return_db(db)
