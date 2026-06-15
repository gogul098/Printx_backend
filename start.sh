#!/usr/bin/env bash
# Start Celery worker in the background
celery -A core worker --loglevel=info &

# Start Gunicorn in the foreground
gunicorn core.wsgi:application
