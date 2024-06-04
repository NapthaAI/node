#!/bin/bash
source /home/ubuntu/node/.venv/bin/activate
exec celery -A node.worker.main.app worker --loglevel=info
