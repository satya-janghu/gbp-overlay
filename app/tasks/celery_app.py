"""Celery application configuration."""

from celery import Celery

from app.config import REDIS_URL

celery = Celery(
    "gbp_overlay",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.tasks.crawl_tasks",
        "app.tasks.generate_tasks",
    ],
)

celery.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    result_expires=86400,
    beat_schedule={
        "cleanup-expired": {
            "task": "app.tasks.celery_app.cleanup_expired_task",
            "schedule": 3600.0,  # every hour
        },
    },
)


@celery.task(name="app.tasks.celery_app.cleanup_expired_task")
def cleanup_expired_task():
    """Periodic task to clean up expired downloads and orphaned files."""
    from app.services.cleanup import run_cleanup
    run_cleanup()
