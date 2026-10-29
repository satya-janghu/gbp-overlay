#!/bin/bash
# start.sh — run both web server and celery worker in one container
# This ensures both processes share the same persistent volume at /data
set -e

# Start Celery worker + beat in background
celery -A app.tasks.celery_app worker --beat --loglevel=info --concurrency=4 &
CELERY_PID=$!

# Start web server in foreground (Railway health checks hit this)
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} &
UVICORN_PID=$!

# Wait for either process to exit, then kill the other
wait -n $CELERY_PID $UVICORN_PID
EXIT_CODE=$?
kill $CELERY_PID $UVICORN_PID 2>/dev/null || true
exit $EXIT_CODE
