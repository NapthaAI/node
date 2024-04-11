#!/bin/bash
source /home/ubuntu/node/.venv/bin/activate
exec celery -A node.celery_worker.celery_worker.app worker --loglevel=info
