"""Shared dependencies for route handlers."""
import os
from datetime import datetime

from fastapi import HTTPException


def require_project_ownership(project, session_id: str) -> None:
    """Raise 403 if the project does not belong to the given session."""
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project["session_id"] != session_id:
        raise HTTPException(status_code=403, detail="Forbidden")


def safe_path(base: str, *parts: str) -> str:
    """Join path parts and verify the result is within base directory.

    Raises HTTPException(400) on path traversal attempts.
    """
    resolved = os.path.realpath(os.path.join(base, *parts))
    base_resolved = os.path.realpath(base)
    if not resolved.startswith(base_resolved + os.sep) and resolved != base_resolved:
        raise HTTPException(status_code=400, detail="Invalid path")
    return resolved


def serialize_for_json(obj):
    """Recursively convert datetime and other non-JSON-safe types."""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, memoryview):
        return None
    return obj
