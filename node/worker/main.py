# worker/main.py
from celery import Celery
from dotenv import load_dotenv
from node.utils import get_logger
from celery.signals import worker_init, worker_shutdown
import os
import asyncio
from node.grpc_pool_manager import get_grpc_pool_instance, close_grpc_pool

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
BACKEND_URL = f"rpc://{RMQ_USER}:{RMQ_PASSWORD}@localhost:5672/"
NUM_GRPC_CONNECTIONS = 300
BUFFER_SIZE = 30

logger.info(f"BROKER_URL: {BROKER_URL}")


@worker_init.connect
def initialize_grpc_pool(**kwargs):
    """
    Initializes the GlobalGrpcPool when a Celery worker starts.
    Starts the monitor_pool coroutine within the worker's event loop.
    """
    logger.info("Initializing GlobalGrpcPool for Celery worker.")
    pool = get_grpc_pool_instance(
        max_channels=NUM_GRPC_CONNECTIONS, buffer_size=BUFFER_SIZE
    )

    # Start the monitor_pool coroutine
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.create_task(pool.monitor_pool())
        logger.info("GlobalGrpcPool initialized and monitor_pool started.")
    except Exception as e:
        logger.error(f"Failed to start monitor_pool: {e}")


@worker_shutdown.connect
def shutdown_grpc_pool_signal(**kwargs):
    """
    Shuts down the GlobalGrpcPool when a Celery worker stops.
    Ensures that all channels are closed gracefully.
    """
    logger.info("Shutting down GlobalGrpcPool for Celery worker.")
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.run_until_complete(close_grpc_pool())
    except Exception as e:
        logger.error(f"Error during gRPC pool shutdown: {e}")
    logger.info("GlobalGrpcPool shut down.")


# Celery app
app = Celery(
    "docker_tasks",
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=["node.worker.template_worker", "node.worker.docker_worker"],
)


@app.on_after_configure.connect
def setup_eventloop(sender, **kwargs):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
