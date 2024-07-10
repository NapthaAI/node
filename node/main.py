import os
import json
import asyncio
import websockets
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from node.storage.db.init_db import init_db
from node.storage.hub.hub import Hub

from node.module_manager import setup_modules_from_config
from node.ollama.init_ollama import setup_ollama
from node.comms.http_server.task import router as http_server_router
from node.comms.http_server.storage import router as http_server_storage_router
from node.comms.http_server.user import router as http_server_user_router
from node.comms.http_server.orchestration import router as http_server_orchestration_router
from node.comms.ws_server.task import create_task_ws, check_task_ws
from node.comms.ws_server.user import register_user_ws, check_user_ws
from node.comms.ws_server.orchestration import create_task_run_ws, update_task_run_ws
from node.comms.ws_server.storage import write_to_ipfs_ws, read_from_ipfs_ws, write_storage_ws, read_storage_ws
from node.utils import get_logger, get_config, get_node_config, create_output_dir


logger = get_logger(__name__)


# Get file path
FILE_PATH = Path(__file__).resolve()
PARENT_DIR = FILE_PATH.parent


# Setup REST API
app = FastAPI()
app.include_router(http_server_router)
app.include_router(http_server_storage_router)
app.include_router(http_server_user_router)
app.include_router(http_server_orchestration_router)


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


async def websocket_handler(uri):
    """Handles persistent WebSocket connection."""
    async with websockets.connect(uri, ping_interval=None) as websocket:
        logger.info("Connected to relay server")
        try:
            while True:
                try:
                    message = await websocket.recv()
                    message = json.loads(message)
                    logger.info(f"Received message from relay server: {message}")

                    if message['source_node'] == message['target_node']:
                        logger.info(f"Source Node is same as target node")
                        
                    if message["path"] == "create_task":
                        await create_task_ws(
                            websocket=websocket, 
                            message=message
                        )
                    elif message["path"] == "check_task":
                        await check_task_ws(
                            websocket=websocket, 
                            message=message
                        )
                    elif message["path"] == "check_user":
                        await check_user_ws(
                            websocket=websocket,
                            message=message
                        )
                    elif message["path"] == "register_user":
                        await register_user_ws(
                            websocket=websocket,
                            message=message
                        )
                    elif message["path"] == "create_task_run":
                        await create_task_run_ws(
                            websocket=websocket,
                            message=message
                        )
                    elif message["path"] == "update_task_run":
                        await update_task_run_ws(
                            websocket=websocket,
                            message=message
                        )
                    elif message["path"] == "write_to_ipfs":
                        await write_to_ipfs_ws(
                            websocket=websocket,
                            message=message
                        )
                    elif message["path"] == "read_from_ipfs":
                        await read_from_ipfs_ws(
                            websocket=websocket,
                            message=message
                        )
                    elif message["path"] == "write_storage":
                        await write_storage_ws(
                            websocket=websocket,
                            message=message
                        )
                    elif message["path"] == "read_storage":
                        await read_storage_ws(
                            websocket=websocket,
                            message=message
                        )
                    else:
                        logger.error(f"Unknown message path: {message}")
                        await websocket.send(json.dumps({
                            'target_node': message['source_node'],
                            'source_node': message['target_node'],
                            'params': {'error': 'Unknown message path'}
                        }))
                except Exception as e:
                    logger.error(f"Error: {e}")
                    response = {
                        'target_node': message['source_node'],
                        'source_node': message['target_node'],
                        'params': {'error': str(e)}
                    }
                    await websocket.send(json.dumps(response))
        except websockets.ConnectionClosed:
            logger.error("WebSocket connection closed unexpectedly")
        except Exception as err:
            logger.error(f"{err}")
            pass

@app.get("/node_id")
async def get_node_id():
    return os.environ["NODE_ID"]


@app.on_event("startup")
async def on_startup():
    global hub
    hub = await Hub()
    hub.node_config = get_node_config(config)
    create_output_dir(config["BASE_OUTPUT_DIR"])
    await setup_ollama(hub.node_config.ollama_models)
    setup_modules_from_config(Path("../node/storage/hub/packages.json"))

    _, _, user_id = await hub.signin()
    hub.node_config.owner = f"{user_id}"
    node_details = hub.node_config.dict()
    node_details.pop("id", None)
    node = await hub.create_node(node_details)
    os.environ["NODE_ID"] = node[0]["id"].split(":")[1]
    logger.info(f"Node ID: {os.environ['NODE_ID']}")
    if node is None:
        raise Exception("Failed to register node")

    if not node_details["ip"]:
        logger.info("Node is indirect")
        uri = f"{node_details['routing']}/ws/{node[0]['id'].split(':')[-1]}"
        asyncio.create_task(websocket_handler(uri))


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
        log_level="debug",
        timeout_keep_alive=300,  # Increase the keep-alive timeout to 300 seconds
        limit_concurrency=200,  # Limit the number of concurrent connections to 200
        backlog=4096,  # Increase the maximum number of pending connections to 4096
    )
