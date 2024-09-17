import asyncio
from dotenv import load_dotenv
import os
from pathlib import Path

from node.server.http.server import HTTPServer
from node.server.ws.server import WebSocketServer
from node.utils import get_logger, get_config, get_node_config

logger = get_logger(__name__)
load_dotenv()

async def run_server():
    config = get_config()
    node_config = get_node_config(config)

    if not node_config.ip:
        logger.info("Node is indirect")
        uri = f"{os.getenv('PUBLIC_HUB_URL')}/ws/{node_config.id.split(':')[-1]}"
        websocket_server = WebSocketServer(uri)
        websocket_server.launch_server()

    http_server = HTTPServer(os.getenv("NODE_IP"), int(os.getenv("NODE_PORT")))
    try:
        await http_server.launch_server()
    except Exception as e:
        logger.error(f"Error during server execution: {e}")
    finally:
        await on_shutdown()


# Unregister the node with the hub on shutdown
async def on_shutdown():
    """
    Unregister the node with the hub on shutdown
    """
    try:
        logger.info("Unregistering node with hub")

        global hub
        logger.info(f"Node Config: {hub.node_config}")
        success = await hub.delete_node(hub.node_config[0]["id"])

        if success:
            logger.info("Deleted node")
        else:
            logger.error("Failed to delete node")
            raise Exception("Failed to delete node")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


if __name__ == "__main__":
    asyncio.run(run_server())
