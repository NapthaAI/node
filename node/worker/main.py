from celery import Celery
from dotenv import load_dotenv
from node.utils import get_logger
import os

logger = get_logger(__name__)

# Load environment variables
load_dotenv(".env")

# Celery config
BROKER_URL = os.environ.get("CELERY_BROKER_URL")

# Make sure OPENAI_API_KEY is set
try:
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    logger.info("OPENAI_API_KEY found in environment")
except KeyError:
    logger.error("OPENAI_API_KEY not found in environment")
    raise Exception("OPENAI_API_KEY not found in environment")

# Celery app
app = Celery(
    "docker_tasks",
    broker=BROKER_URL,
    include=['node.worker.template_worker', 'node.worker.docker_worker'],
)