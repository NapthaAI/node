from celery import Celery
from dotenv import load_dotenv
from node.utils import get_logger
import os

logger = get_logger(__name__)

# Load environment variables
load_dotenv(".env")

# Make sure OPENAI_API_KEY is set
try:
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    logger.info("OPENAI_API_KEY found in environment")
except KeyError:
    logger.error("OPENAI_API_KEY not found in environment")
    raise Exception("OPENAI_API_KEY not found in environment")

# Celery config
RMQ_USER = os.environ.get("RMQ_USER")
RMQ_PASSWORD = os.environ.get("RMQ_PASSWORD")
BROKER_URL = f"amqp://{RMQ_USER}:{RMQ_PASSWORD}@localhost:5672/"

logger.info(f"BROKER_URL: {BROKER_URL}")

# Celery app
app = Celery(
    "docker_tasks",
    broker=BROKER_URL,
    include=['node.worker.template_worker', 'node.worker.docker_worker'],
)

# # At the end of your node/worker/main.py file, add:

# app.conf.update(
#     broker_url=BROKER_URL,
# )

# print(f"Celery app broker URL: {app.conf.broker_url}")