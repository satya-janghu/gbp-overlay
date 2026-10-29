"""CRUD helper functions for database operations.

Each function takes a psycopg2 connection as its first argument.
"""

import logging

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection, quote_ident

logger = logging.getLogger(__name__)


def _cursor(db: PgConnection):
    """Return a RealDictCursor for the given connection."""
    return db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def get_or_create_session(db, session_id: str) -> dict:
    """Return existing session or create a new one. Updates last_seen_at.

    Caller is responsible for calling db.commit().
    """
    with _cursor(db) as cur:
        cur.execute(
            "SELECT * FROM sessions WHERE session_id = %s", (session_id,)
        )
        row = cur.fetchone()

        if row is None:
            cur.execute(
                "INSERT INTO sessions (session_id) VALUES (%s)",
                (session_id,),
            )
            db.commit()
            cur.execute(
                "SELECT * FROM sessions WHERE session_id = %s", (session_id,)
            )
            row = cur.fetchone()
        else:
            cur.execute(
                "UPDATE sessions SET last_seen_at = CURRENT_TIMESTAMP WHERE session_id = %s",
                (session_id,),
            )
            db.commit()

    return row


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def create_project(
    db,
    session_id: str,
    client_name: str,
    website_url: str,
    keywords_json: str,
    locations_json: str | None,
    font: str,
    images_per_page: int,
    fetch_anywhere: bool,
    js_rendered: bool,
) -> int:
    """Insert a new project and return its id."""
    with _cursor(db) as cur:
        cur.execute(
            """INSERT INTO projects
               (session_id, client_name, website_url, keywords, locations,
                font, images_per_page, fetch_anywhere, js_rendered)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                session_id,
                client_name,
                website_url,
                keywords_json,
                locations_json,
                font,
                images_per_page,
                fetch_anywhere,
                js_rendered,
            ),
        )
        return cur.fetchone()["id"]


def get_project(db, project_id: int) -> dict | None:
    """Return a single project by id."""
    with _cursor(db) as cur:
        cur.execute(
            "SELECT * FROM projects WHERE id = %s", (project_id,)
        )
        return cur.fetchone()


def get_session_projects(db, session_id: str) -> list[dict]:
    """Return all projects for a session, newest first."""
    with _cursor(db) as cur:
        cur.execute(
            "SELECT * FROM projects WHERE session_id = %s ORDER BY created_at DESC",
            (session_id,),
        )
        return cur.fetchall()


def update_project_status(
    db,
    project_id: int,
    status: str,
    celery_task_id: str | None = None,
) -> None:
    """Update a project's status and optionally its celery_task_id."""
    with _cursor(db) as cur:
        if celery_task_id is not None:
            cur.execute(
                "UPDATE projects SET status = %s, celery_task_id = %s WHERE id = %s",
                (status, celery_task_id, project_id),
            )
        else:
            cur.execute(
                "UPDATE projects SET status = %s WHERE id = %s",
                (status, project_id),
            )


def update_project_status_if(
    db,
    project_id: int,
    new_status: str,
    allowed_statuses: tuple[str, ...],
    celery_task_id: str | None = None,
) -> int:
    """Atomically update project status only if current status is in allowed_statuses.

    Returns the number of rows updated (0 if status didn't match).
    Caller is responsible for calling db.commit().
    """
    placeholders = ", ".join(["%s"] * len(allowed_statuses))
    with _cursor(db) as cur:
        if celery_task_id is not None:
            cur.execute(
                f"UPDATE projects SET status = %s, celery_task_id = %s"
                f" WHERE id = %s AND status IN ({placeholders})",
                (new_status, celery_task_id, project_id, *allowed_statuses),
            )
        else:
            cur.execute(
                f"UPDATE projects SET status = %s"
                f" WHERE id = %s AND status IN ({placeholders})",
                (new_status, project_id, *allowed_statuses),
            )
        return cur.rowcount


# ---------------------------------------------------------------------------
# Project Images
# ---------------------------------------------------------------------------

def add_project_image(db, project_id: int, **kwargs) -> int:
    """Insert a project image row and return its id.

    kwargs may include any column from project_images except id and project_id.
    """
    allowed = {
        "source_url", "source_page_url", "location", "keyword",
        "image_hash", "classification", "confidence", "overlay_position",
        "original_path", "processed_path", "status", "width", "height",
        "page_title", "page_meta_description",
    }
    unknown = set(kwargs) - allowed
    if unknown:
        logger.warning("add_project_image: ignoring unknown kwargs: %s", unknown)
    filtered = {k: v for k, v in kwargs.items() if k in allowed}

    # Defense-in-depth: verify keys are valid identifiers
    for k in filtered:
        if not k.isidentifier() or k not in allowed:
            raise ValueError(f"Invalid column name: {k}")

    columns = ["project_id"] + list(filtered.keys())
    values = [project_id] + list(filtered.values())

    with _cursor(db) as cur:
        col_str = ", ".join(quote_ident(c, cur) for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        cur.execute(
            f"INSERT INTO project_images ({col_str}) VALUES ({placeholders}) RETURNING id",
            values,
        )
        return cur.fetchone()["id"]


def update_project_image(db, image_id: int, **kwargs) -> None:
    """Update fields on a project image row."""
    allowed = {
        "source_url", "source_page_url", "location", "keyword",
        "image_hash", "classification", "confidence", "overlay_position",
        "original_path", "processed_path", "status", "width", "height",
        "page_title", "page_meta_description",
    }
    unknown = set(kwargs) - allowed
    if unknown:
        logger.warning("update_project_image: ignoring unknown kwargs: %s", unknown)
    filtered = {k: v for k, v in kwargs.items() if k in allowed}
    if not filtered:
        return

    # Defense-in-depth: verify keys are valid identifiers
    for k in filtered:
        if not k.isidentifier() or k not in allowed:
            raise ValueError(f"Invalid column name: {k}")

    values = list(filtered.values()) + [image_id]

    with _cursor(db) as cur:
        set_clause = ", ".join(f"{quote_ident(k, cur)} = %s" for k in filtered)
        cur.execute(
            f"UPDATE project_images SET {set_clause} WHERE id = %s",
            values,
        )


def get_project_images(
    db,
    project_id: int,
    status: str | None = None,
) -> list[dict]:
    """Return images for a project, optionally filtered by status."""
    with _cursor(db) as cur:
        if status is not None:
            cur.execute(
                "SELECT * FROM project_images WHERE project_id = %s AND status = %s",
                (project_id, status),
            )
        else:
            cur.execute(
                "SELECT * FROM project_images WHERE project_id = %s",
                (project_id,),
            )
        return cur.fetchall()


def get_image(db, image_id: int) -> dict | None:
    """Return a single project image by id."""
    with _cursor(db) as cur:
        cur.execute(
            "SELECT * FROM project_images WHERE id = %s", (image_id,)
        )
        return cur.fetchone()


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

def create_download(
    db,
    project_id: int,
    session_id: str,
    client_name: str,
    image_count: int,
    zip_path: str,
    zip_size: int,
    expires_at: str,
) -> int:
    """Insert a download record and return its id."""
    with _cursor(db) as cur:
        cur.execute(
            """INSERT INTO downloads
               (project_id, session_id, client_name, image_count, zip_path, zip_size, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (project_id, session_id, client_name, image_count, zip_path, zip_size, expires_at),
        )
        return cur.fetchone()["id"]


def get_download_for_project(db, session_id: str, project_id: int) -> dict | None:
    """Return the latest download for a project."""
    with _cursor(db) as cur:
        cur.execute(
            """SELECT id, project_id, session_id, client_name, image_count,
                      zip_path, zip_size, created_at, expires_at
               FROM downloads
               WHERE session_id = %s AND project_id = %s
               ORDER BY created_at DESC LIMIT 1""",
            (session_id, project_id),
        )
        return cur.fetchone()


def get_session_downloads(db, session_id: str) -> list[dict]:
    """Return all downloads for a session, newest first."""
    with _cursor(db) as cur:
        cur.execute(
            """SELECT id, project_id, session_id, client_name, image_count,
                      zip_path, zip_size, created_at, expires_at
               FROM downloads WHERE session_id = %s ORDER BY created_at DESC""",
            (session_id,),
        )
        return cur.fetchall()


def get_expired_downloads(db) -> list[dict]:
    """Return downloads whose files have expired but haven't been cleaned up yet."""
    with _cursor(db) as cur:
        cur.execute(
            """SELECT id, project_id, zip_path FROM downloads
               WHERE expires_at < CURRENT_TIMESTAMP
               AND zip_path IS NOT NULL"""
        )
        return cur.fetchall()
