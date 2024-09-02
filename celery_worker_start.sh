#!/bin/bash
source /Users/arshath/play/node/.venv/bin/activate
exec celery -A node.worker.main.app worker --loglevel=info
