import asyncio
from dotenv import load_dotenv
from pathlib import Path

from node.comms.http_server.server import HTTPServer
from node.comms.ws_server.server import WebSocketServer
from node.module_manager import setup_modules_from_config
from node.storage.db.init_db import init_db
from node.storage.hub.hub import Hub
from node.utils import get_logger, get_config, get_node_config, create_output_dir


logger = get_logger(__name__)

FILE_PATH = Path(__file__).resolve()
PARENT_DIR = FILE_PATH.parent


async def run_node():
    """
    Main function for running the node. This function initializes the database,
    loads environment variables, sets up the node configuration, initializes modules,
    creates a Hub instance, registers the node, and launches either a WebSocket server
    (for indirect nodes) or an HTTP server (for direct nodes). It also handles graceful
    shutdown of the node.
    """
    init_db()

    load_dotenv(".env.node")
    config = get_config()
    node_config = get_node_config(config)

    create_output_dir(config["BASE_OUTPUT_DIR"])
    setup_modules_from_config(Path(f"{PARENT_DIR}/storage/hub/packages.json"))

    hub = await Hub()
    node_config = await hub.create_node(node_config)

    if not node_config["ip"]:
        logger.info("Node is indirect")
        uri = f"{node_config['routing']}/ws/{node_config['id'].split(':')[-1]}"
        websocket_server = WebSocketServer(uri)
        websocket_server.launch_server()

    http_server = HTTPServer(node_config["ip"], node_config["port"], node_config["id"])
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
    asyncio.run(run_node())
