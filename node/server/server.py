import asyncio
from dotenv import load_dotenv
import os
import socket
import logging
from pathlib import Path

from node.config import get_node_config, NODE_ROUTING
from node.storage.hub.hub import Hub
from node.server.http_server import HTTPServer
from node.server.ws_server import WebSocketServer
from node.server.grpc_server import GrpcServer
from node.utils import setup_logging


setup_logging()
logger = logging.getLogger(__name__)
load_dotenv()

FILE_PATH = Path(__file__).resolve()
PARENT_DIR = FILE_PATH.parent

hub = None
LEAD_SERVER = None


def find_available_port(start_port: int = 7001) -> int:
    """Find an available port starting from start_port."""
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
            port += 1


async def run_server(port: int):
    global hub, LEAD_SERVER

    node_config = get_node_config()
    node_id = node_config.id.split(":")[1]
    ports = node_config.ports

    if port == ports[-1]:
        LEAD_SERVER = True
    else:
        LEAD_SERVER = False

    if node_config.node_type == "indirect":
        logger.info("Creating indirect websocket server...")
        uri = f"{NODE_ROUTING}/ws/{node_id}"
        server = WebSocketServer(
            uri, port, node_type=node_config.node_type, node_id=node_id
        )

    elif node_config.node_type == "direct":
        if node_config.server_type == "http":
            logger.info(f"Creating direct HTTP server on port {port}...")
            if "http://" in node_config.ip:
                ip = node_config.ip.split("//")[1]
            else:
                ip = node_config.ip
            server = HTTPServer(ip, port)

        elif node_config.server_type == "ws":
            logger.info(f"Creating direct WebSocket server on port {port}...")
            server = WebSocketServer(
                node_config.ip, port, node_config.node_type, node_id=node_id
            )

        elif node_config.server_type == "grpc":
            logger.info(f"Creating direct GRPC server on port {port}...")
            server = GrpcServer(
                node_config.ip, port, node_config.node_type, node_id=node_id
            )

    else:
        raise Exception(f"Invalid node type: {node_config.node_type}")

    # Create and sign in to the hub
    async with Hub() as hub:
        success, user, user_id = await hub.signin(
            os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
        )
        if LEAD_SERVER:
            node_config = await hub.create_node(node_config=node_config)

    if not success:
        logger.error("Failed to sign in to the hub")
        return

    try:
        await server.launch_server()
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
        global hub, LEAD_SERVER
        if LEAD_SERVER:
            node_config = hub.node_config
            if isinstance(node_config, dict):
                node_id = node_config["id"]
            else:
                node_id = node_config.id
            logger.info(f"Node ID: {node_id}")
            logger.info(f"Node Config: {node_config}")

            async with Hub() as hub:
                success, user, user_id = await hub.signin(
                    os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                )
                success = await hub.delete_node(node_id=node_id)

            if success:
                logger.info("Deleted node")
            else:
                logger.error("Failed to delete node")
                raise Exception("Failed to delete node")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run server with specified port")
    parser.add_argument(
        "--port", type=int, default=7001, help="Port number to run the server on"
    )
    args = parser.parse_args()

    asyncio.run(run_server(port=args.port))
