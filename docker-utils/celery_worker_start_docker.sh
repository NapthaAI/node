#!/bin/bash
set -x
# Start Celery with explicit broker URL
exec celery -A node.worker.main:app worker --loglevel=info