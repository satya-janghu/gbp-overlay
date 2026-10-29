"""Async crawling and unified pipeline tasks."""
import json
import os
import time
import logging
import psycopg2
import requests as http_requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from celery import shared_task
from app.database import get_db, return_db
from app import models
from app.services import crawler, image_processor, location_resolver, gemini_client, overlay_renderer
from app.config import (
    DATA_DIR, CRAWL_RATE_LIMIT, CRAWL_CONCURRENCY,
    MAX_IMAGES_PER_PROJECT, MAX_PAGES_TO_CRAWL,
)

logger = logging.getLogger(__name__)

# Stage weights for progress calculation: stage_number -> (start_pct, end_pct)
STAGE_WEIGHTS = {1: (0, 40), 2: (40, 50), 3: (50, 80), 4: (80, 100)}

# Chunk size for streaming images to classification
_CLASSIFY_CHUNK_SIZE = 50


@shared_task(bind=True, name="process_pipeline")
def process_pipeline(self, project_id: int, skip_crawl: bool = False):
    """Unified pipeline: crawl + classify + resolve locations + generate previews.

    Runs the whole pipeline as a single Celery task.

    Progress stages:
        0-40%: Crawling (fetch sitemap, crawl pages, download images, dedup)
        40-50%: Location Detection (AI-powered location page identification)
        50-80%: Classifying (Gemini image classification)
        80-100%: Resolving & Previews (resolve locations, generate preview overlays)
    """
    db = get_db()
    try:
        project = models.get_project(db, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        models.update_project_status(db, project_id, "processing", self.request.id)
        db.commit()

        keywords = json.loads(project["keywords"])
        font_name = project["font"] or "Montserrat"

        def update_progress(stage, stage_number, total_stages, message, current=0, total=0):
            start_pct, end_pct = STAGE_WEIGHTS.get(stage_number, (0, 100))
            if total > 0:
                stage_pct = current / total
            else:
                stage_pct = 0
            overall = start_pct + (end_pct - start_pct) * stage_pct
            self.update_state(state="PROGRESS", meta={
                "stage": stage,
                "stage_number": stage_number,
                "total_stages": total_stages,
                "message": message,
                "current": current,
                "total": total,
                "overall_progress": int(overall),
            })

        # ── Stage 1: Crawling (0-40%) ──────────────────────────────────
        all_hashes = {}
        page_metadata = []  # For location detection

        if not skip_crawl and project["website_url"]:
            update_progress("crawling", 1, 4, "Fetching sitemap...", 0, 0)

            website_url = project["website_url"]
            images_per_page = project["images_per_page"] or 1
            fetch_anywhere = bool(project["fetch_anywhere"])
            js_rendered = bool(project["js_rendered"])

            robot_parser = crawler._check_robots(website_url)
            pages = crawler.fetch_sitemap(website_url)

            if not pages:
                pages = [{"url": website_url, "images": [], "is_location": False, "location": None}]

            # Enforce MAX_PAGES_TO_CRAWL
            if len(pages) > MAX_PAGES_TO_CRAWL:
                logger.info("Capping crawl from %d to %d pages for project %d",
                            len(pages), MAX_PAGES_TO_CRAWL, project_id)
                pages = pages[:MAX_PAGES_TO_CRAWL]

            # Don't filter by location patterns yet — AI will detect locations
            if not fetch_anywhere:
                pass  # Keep all pages for now, AI will identify locations

            total_pages = len(pages)
            image_counter = len(models.get_project_images(db, project_id))

            # Concurrent crawling with ThreadPoolExecutor
            rate_limiter = crawler.DomainRateLimiter(CRAWL_RATE_LIMIT)
            http_session = crawler._make_session()
            upload_dir = os.path.join(DATA_DIR, "uploads", str(project_id))
            os.makedirs(upload_dir, exist_ok=True)

            completed_pages = 0
            hit_image_limit = False

            with ThreadPoolExecutor(max_workers=CRAWL_CONCURRENCY) as executor:
                futures = {
                    executor.submit(
                        crawler.crawl_page_batch,
                        page=page,
                        images_per_page=images_per_page,
                        js_rendered=js_rendered,
                        robot_parser=robot_parser,
                        rate_limiter=rate_limiter,
                        session=http_session,
                    ): page
                    for page in pages
                }

                for future in as_completed(futures):
                    completed_pages += 1

                    # Check image limit before processing more results
                    if hit_image_limit:
                        continue

                    try:
                        result = future.result()
                    except Exception as e:
                        page_info = futures[future]
                        logger.warning("Crawl failed for %s: %s", page_info.get("url", "?"), e)
                        continue

                    update_progress("crawling", 1, 4,
                        f"Crawled page {completed_pages}/{total_pages}: "
                        f"{result['page_url'][:60]}...",
                        completed_pages, total_pages)

                    # Store page metadata for location detection
                    page_metadata.append({
                        "url": result["page_url"],
                        "title": result["page_title"],
                        "meta_description": result["page_meta"],
                        "url_location": result["url_location"],
                        "url_is_location": result["url_is_location"],
                    })

                    # Write downloaded images to DB (serialized in main thread)
                    for dl in result["downloaded"]:
                        # Enforce MAX_IMAGES_PER_PROJECT
                        if image_counter >= MAX_IMAGES_PER_PROJECT:
                            logger.info("Hit image limit (%d) for project %d",
                                        MAX_IMAGES_PER_PROJECT, project_id)
                            hit_image_limit = True
                            break

                        image_counter += 1
                        img_filename = f"proj{project_id}_{image_counter}.jpg"
                        img_path = os.path.join(upload_dir, img_filename)

                        jpeg_data = image_processor.convert_to_jpeg(dl["img_data"])
                        with open(img_path, "wb") as f:
                            f.write(jpeg_data)

                        img_id = models.add_project_image(
                            db, project_id,
                            source_url=dl["img_url"],
                            source_page_url=result["page_url"],
                            location=result["url_location"],
                            image_hash=dl["img_hash"],
                            original_path=img_path,
                            status="pending",
                            width=dl["width"],
                            height=dl["height"],
                            page_title=result["page_title"],
                            page_meta_description=result["page_meta"],
                        )

                        all_hashes[img_id] = dl["img_hash"]

                # Single commit after all images are inserted
                db.commit()

            # Deduplication
            update_progress("crawling", 1, 4, "Removing duplicate images...",
                            total_pages, total_pages)
            duplicates = image_processor.find_duplicates(all_hashes)
            for dup_id in duplicates:
                models.update_project_image(db, dup_id, status="duplicate")
            db.commit()

        # ── Stage 2: AI Location Detection (40-50%) ───────────────────
        update_progress("location_detection", 2, 4,
                        "Detecting location pages with AI...", 0, 1)

        if page_metadata:
            try:
                ai_locations = gemini_client.detect_location_pages(page_metadata)

                # Build a URL -> location map from AI results
                ai_location_map = {}
                for result in ai_locations:
                    if result["is_location"] and result["location"]:
                        ai_location_map[result["url"]] = result["location"]

                # Update images with AI-detected locations
                active_images = [
                    dict(img) for img in models.get_project_images(db, project_id)
                    if img["status"] not in ("duplicate", "skipped")
                ]
                for img in active_images:
                    page_url = img.get("source_page_url")
                    if page_url and page_url in ai_location_map:
                        # AI location takes priority over URL-pattern location
                        models.update_project_image(
                            db, img["id"], location=ai_location_map[page_url]
                        )
                db.commit()
            except (psycopg2.OperationalError, psycopg2.DatabaseError):
                raise  # Let DB errors propagate to pipeline error handler
            except Exception as e:
                logger.warning("AI location detection failed, falling back to URL patterns: %s", e)

        update_progress("location_detection", 2, 4,
                        "Location detection complete", 1, 1)

        # ── Stage 3: Classification (50-80%) ──────────────────────────
        pending_images = models.get_project_images(db, project_id, status="pending")

        if not pending_images:
            # No images to classify
            update_progress("classifying", 3, 4, "No images to classify", 0, 0)
        elif len(keywords) == 1:
            # Single-keyword shortcut: auto-assign all
            update_progress("classifying", 3, 4,
                            f"Auto-assigning keyword: {keywords[0]}", 0, len(pending_images))
            for img in pending_images:
                models.update_project_image(
                    db, img["id"],
                    keyword=keywords[0],
                    confidence=1.0,
                    status="classified",
                )
            db.commit()
            update_progress("classifying", 3, 4,
                            "Classification complete", len(pending_images), len(pending_images))
        else:
            # Stream images to classification in chunks instead of loading all at once.
            total_pending = len(pending_images)
            classified_count = 0

            def classify_progress_cb(current, batch_total):
                update_progress("classifying", 3, 4,
                    f"Classifying image {classified_count + current}/{total_pending}...",
                    classified_count + current, total_pending)

            for chunk_start in range(0, total_pending, _CLASSIFY_CHUNK_SIZE):
                chunk = pending_images[chunk_start:chunk_start + _CLASSIFY_CHUNK_SIZE]
                image_batch = []

                for img in chunk:
                    img_bytes = None
                    if img["original_path"]:
                        try:
                            with open(img["original_path"], "rb") as f:
                                img_bytes = f.read()
                        except FileNotFoundError:
                            pass
                    if img_bytes is None and img.get("source_url"):
                        try:
                            resp = http_requests.get(img["source_url"], timeout=15)
                            resp.raise_for_status()
                            img_bytes = resp.content
                        except Exception as e:
                            logger.error("Failed to download image %d: %s", img["id"], e)
                    if img_bytes:
                        try:
                            resized = image_processor.resize_for_api(img_bytes)
                            image_batch.append((img["id"], resized))
                        except Exception as e:
                            logger.error("Failed to process image %d: %s", img["id"], e)
                            models.update_project_image(db, img["id"], status="skipped")
                    else:
                        models.update_project_image(db, img["id"], status="skipped")

                if image_batch:
                    results = gemini_client.classify_batch(
                        image_batch, keywords, classify_progress_cb
                    )

                    for image_id, result in results.items():
                        kw = result.get("keyword")
                        conf = result.get("confidence", 0)
                        if kw and conf >= 0.4:
                            models.update_project_image(
                                db, image_id,
                                keyword=kw,
                                confidence=conf,
                                classification=result.get("description", ""),
                                status="classified",
                            )
                        else:
                            models.update_project_image(
                                db, image_id,
                                keyword=kw,
                                confidence=conf,
                                classification=result.get("description", ""),
                                status="auto_skipped",
                            )

                classified_count += len(chunk)
                db.commit()  # Commit per chunk

        # ── Stage 4: Resolve Locations & Generate Previews (80-100%) ──
        update_progress("resolving", 4, 4, "Resolving locations...", 0, 2)

        # Resolve remaining locations
        active_images = [
            dict(img) for img in models.get_project_images(db, project_id)
            if img["status"] in ("classified", "confirmed")
        ]
        raw_locations = [img["location"] for img in active_images if img.get("location")]
        if raw_locations:
            context = location_resolver.build_context_profile(raw_locations)
            for img in active_images:
                loc = img.get("location")
                if loc:
                    resolved = location_resolver.resolve_location(
                        loc, context=context, known_locations=raw_locations
                    )
                    if resolved != loc:
                        models.update_project_image(db, img["id"], location=resolved)
            db.commit()

        # If project has user-specified locations and images have no location, assign first one
        try:
            project_locations = json.loads(project["locations"] or "[]")
        except (json.JSONDecodeError, TypeError):
            project_locations = []

        if project_locations:
            unlocated = [img for img in active_images if not img.get("location")]
            for i, img in enumerate(unlocated):
                models.update_project_image(
                    db, img["id"],
                    location=project_locations[i % len(project_locations)],
                )
            db.commit()

        # Page-metadata location fallback: try page title / meta description
        still_missing = [
            dict(img) for img in models.get_project_images(db, project_id)
            if img["status"] in ("classified", "confirmed") and not img.get("location")
        ]
        if still_missing:
            for img in still_missing:
                loc = location_resolver.extract_location_from_text(
                    img.get("page_title") or ""
                )
                if not loc:
                    loc = location_resolver.extract_location_from_text(
                        img.get("page_meta_description") or ""
                    )
                if loc:
                    models.update_project_image(db, img["id"], location=loc)
            db.commit()

        update_progress("resolving", 4, 4, "Generating preview overlays...", 1, 2)

        # Generate preview overlays for all classified images
        preview_images = [
            dict(img) for img in models.get_project_images(db, project_id)
            if img["status"] in ("classified", "confirmed") and img.get("keyword")
        ]

        preview_dir = os.path.join(DATA_DIR, "processed", str(project_id))
        os.makedirs(preview_dir, exist_ok=True)

        # Pre-flight: verify font files exist
        from app.config import FONT_DIR, FONTS
        font_files = FONTS.get(font_name, {})
        for weight, filename in font_files.items():
            font_path = os.path.join(FONT_DIR, filename)
            if not os.path.exists(font_path):
                logger.error("Font file missing: %s (font=%s, weight=%s)", font_path, font_name, weight)

        total_previews = len(preview_images)
        preview_success = 0
        preview_failed = 0

        for idx, img in enumerate(preview_images):
            if img["original_path"] and os.path.exists(img["original_path"]):
                preview_path = os.path.join(preview_dir, f"preview_{img['id']}.jpg")
                try:
                    overlay_renderer.render_overlay(
                        image_path=img["original_path"],
                        keyword=img["keyword"],
                        location=img.get("location") or "",
                        font_name=font_name,
                        output_path=preview_path,
                    )
                    # Store processed_path in DB for diagnostics
                    models.update_project_image(db, img["id"], processed_path=preview_path)
                    preview_success += 1
                except Exception as e:
                    preview_failed += 1
                    logger.exception("Preview generation failed for image %d in project %d",
                                     img["id"], project_id)
            else:
                preview_failed += 1
                logger.warning("Original file missing for image %d: %s (exists=%s)",
                               img["id"], img.get("original_path"),
                               os.path.exists(img["original_path"]) if img.get("original_path") else False)

            # Report progress every 10 images
            if (idx + 1) % 10 == 0 or idx + 1 == total_previews:
                pct = 1 + (idx + 1) / max(total_previews, 1)
                update_progress("resolving", 4, 4,
                                f"Generating previews ({idx + 1}/{total_previews})...",
                                pct, 2)

        if total_previews > 0:
            db.commit()
        logger.info("Preview generation for project %d: %d/%d succeeded, %d failed",
                     project_id, preview_success, total_previews, preview_failed)

        update_progress("resolving", 4, 4, "Pipeline complete!", 2, 2)

        # Update project status to review
        models.update_project_status(db, project_id, "review")
        db.commit()

        # Summarize results
        all_images = models.get_project_images(db, project_id)
        classified = len([i for i in all_images if i["status"] in ("classified", "confirmed")])
        auto_skipped = len([i for i in all_images if i["status"] == "auto_skipped"])
        duplicates_count = len([i for i in all_images if i["status"] == "duplicate"])

        return {
            "project_id": project_id,
            "total_images": len(all_images),
            "classified": classified,
            "auto_skipped": auto_skipped,
            "duplicates": duplicates_count,
        }

    except Exception as e:
        logger.error("Pipeline failed for project %d: %s", project_id, e)
        try:
            db.rollback()
            models.update_project_status(db, project_id, "failed")
            db.commit()
        except Exception:
            logger.error("Failed to update project status to 'failed'")
        raise
    finally:
        return_db(db)

