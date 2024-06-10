from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from pathlib import Path

from node.storage.db.init_db import init_db
from node.storage.hub.hub import Hub

# from node.storage.hub.init_hub import init_hub
from node.module_manager import setup_modules_from_config
from node.ollama.init_ollama import setup_ollama
from node.routes.task import router as task_router
from node.routes.storage import router as storage_router
from node.routes.user import router as user_router
from node.routes.orchestration import router as orchestration_router
from node.utils import get_logger, get_config, get_node_config, create_output_dir

logger = get_logger(__name__)

# Get file path
FILE_PATH = Path(__file__).resolve()
PARENT_DIR = FILE_PATH.parent


# Setup REST API
app = FastAPI()
app.include_router(task_router)
app.include_router(storage_router)
app.include_router(user_router)
app.include_router(orchestration_router)

# Setup CORS
origins = [
    "*",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# init the database
init_db()
config = get_config()

hub = None


@app.on_event("startup")
async def on_startup():
    """
    Register the node with the hub on startup
    """
    global hub
    hub = await Hub()
    logger.info(f"Token: {hub.token}")
    logger.info(f"User ID: {hub.user_id}")

    hub.node_config = get_node_config(config)
    logger.info(f"Node Config: {hub.node_config}")
    create_output_dir(config["BASE_OUTPUT_DIR"])

    await setup_ollama(hub.node_config.ollama_models)

    # Setup Modules
    module_config_path = Path("../node/storage/hub/packages.json")
    setup_modules_from_config(module_config_path)

    # Register node with hub
    _, _, user_id = await hub.signin()
    hub.node_config.owner = f"{user_id}"
    node_details = hub.node_config.dict()
    node_details.pop("id", None)

    node = await hub.create_node(node_details)
    if node is None:
        raise Exception("Failed to register node")

    logger.info(f"Node: {node}")
    logger.info(f"Node config: {hub.node_config}")


# Unregister the node with the hub on shutdown
@app.on_event("shutdown")
async def on_shutdown():
    """
    Unregister the node with the hub on shutdown
    """
    logger.info("Unregistering node with hub")

    global hub
    logger.info(f"Node Config: {hub.node_config}")
    success = await hub.delete_node(hub.node_config[0]["id"])

    if success:
        logger.info("Deleted node")
    else:
        logger.error("Failed to delete node")
        raise Exception("Failed to delete node")


if __name__ == "__main__":
    import uvicorn

    load_dotenv(".env.node")

    port = int(os.getenv("PORT", 7001))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        timeout_keep_alive=15,  # Keep-alive timeout
        # http_lifespan=60,  # HTTP lifespan timeout
        # limit_concurrency=100,  # Limit on the number of concurrent connections
        # backlog=2048,  # Maximum number of pending connections
        # shutdown_timeout=30  # Graceful shutdown timeout
    )
