import asyncio
from dotenv import load_dotenv
import os
import socket
from pathlib import Path

from node.config import get_node_config, NODE_ROUTING
from node.storage.hub.hub import Hub
from node.server.http_server import HTTPServer
from node.server.ws_server import WebSocketServer
from node.utils import get_logger


logger = get_logger(__name__)
load_dotenv()

FILE_PATH = Path(__file__).resolve()
PARENT_DIR = FILE_PATH.parent

http_servers = []
websocket_server = None
hub = None

def find_available_port(start_port: int = 7001) -> int:
    """Find an available port starting from start_port."""
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
            port += 1

async def run_servers():
    global http_servers, websocket_server, hub
    
    node_config = get_node_config()
    node_id = node_config.public_key.split(':')[-1]

    tasks = []

    if node_config.node_type == "indirect": 
        logger.info("Creating indirect websocket server...")
        uri = f"{NODE_ROUTING}/ws/{node_id}"
        websocket_server = WebSocketServer(uri, 7001, node_type =node_config.node_type, node_id=node_id)
        tasks.append(websocket_server.launch_server())

    elif node_config.node_type == "direct" and node_config.server_type == "http":
        logger.info("Creating direct http server...")
        start_port = node_config.ports[0] if node_config.ports else 7001
        actual_ports = []

        for i in range(node_config.num_servers):
            port = find_available_port(start_port)
            http_server = None
            while not http_server:
                try:
                    http_server = HTTPServer(node_config.ip, port)
                    http_servers.append(http_server)
                    actual_ports.append(port)
                    tasks.append(http_server.launch_server())
                    logger.info(f"Launching HTTP server {i+1} on port {port}")
                except Exception as e:
                    logger.warning(f"Failed to launch server on port {port}: {e}")
                    port = find_available_port(port + 1)

            start_port = port + 1  # Set the next start port

        node_config.ports = actual_ports

    elif node_config.node_type == "direct" and node_config.server_type == "ws":
        logger.info("Creating direct websocket server...")
        start_port = node_config.ports[0] if node_config.ports else 7001
        actual_ports = []
        for i in range(node_config.num_servers):
            port = find_available_port(start_port)
            websocket_server = WebSocketServer(node_config.ip, port, node_config.node_type, node_id=node_id)
            tasks.append(websocket_server.launch_server())
            actual_ports.append(port)
            start_port = port + 1  # Set the next start port

        node_config.ports = actual_ports
    else:
        raise Exception(f"Invalid node type: {node_config.node_type}")

    # Create and sign in to the hub
    async with Hub() as hub:
        success, user, user_id = await hub.signin(os.getenv('HUB_USERNAME'), os.getenv('HUB_PASSWORD'))
        node_config = await hub.create_node(node_config)
        logger.info(f"Node Config: {node_config}")
    
    if not success:
        logger.error("Failed to sign in to the hub")
        return
    
    try:
        await asyncio.gather(*tasks)
        logger.info("Servers launched successfully")
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
    asyncio.run(run_servers())
