import asyncio
from dotenv import load_dotenv
import os
import signal
from pathlib import Path
from typing import Optional

from node.config import get_node_config
from node.storage.hub.hub import Hub
from node.server.http_server import HTTPServer
from node.server.ws_server import WebSocketServer
from node.server.grpc_server import GrpcServer
from node.utils import get_logger

logger = get_logger(__name__)
load_dotenv()

FILE_PATH = Path(__file__).resolve()
PARENT_DIR = FILE_PATH.parent

class NodeServer:
    def __init__(self, server_type: str, port: int):
        self.node_config = get_node_config()
        self.node_id = self.node_config.id.split(":")[1]
        # Store initial config values
        self.ip = self.node_config.ip
        self.type = self.node_config.node_type
        self.server: Optional[HTTPServer | WebSocketServer | GrpcServer] = None
        self.server_type = server_type
        self.port = port
        self.hub = None
        self.shutdown_event = asyncio.Event()

    async def register_node(self):
        """Register the node with the hub - only HTTP server does this"""
        if self.server_type == "http":
            async with Hub() as hub:
                self.hub = hub
                success, user, user_id = await hub.signin(
                    os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                )
                if not success:
                    raise Exception("Failed to sign in to hub")
                
                # After registration, node_config might be returned as dict
                self.node_config = await hub.create_node(node_config=self.node_config)
                # Update stored values if node_config is returned as dict
                if isinstance(self.node_config, dict):
                    self.node_id = self.node_config["id"].split(":")[1]
                    self.ip = self.node_config["ip"]
                    self.type = self.node_config["node_type"]
                logger.info(f"Registered node: {self.node_config['id'] if isinstance(self.node_config, dict) else self.node_config.id}")

    async def start_server(self):
        """Start the server based on type and port"""
        # Handle http:// prefix in ip
        if "http://" in self.ip:
            ip = self.ip.split("//")[1]
        else:
            ip = self.ip

        if self.server_type == "http":
            logger.info(f"Starting HTTP server on port {self.port}...")
            self.server = HTTPServer(ip, self.port)
        elif self.server_type == "ws":
            logger.info(f"Starting WebSocket server on port {self.port}...")
            self.server = WebSocketServer(
                ip, 
                self.port,
                node_type=self.type,
                node_id=self.node_id
            )
        elif self.server_type == "grpc":
            logger.info(f"Starting gRPC server on port {self.port}...")
            self.server = GrpcServer(
                ip,
                self.port,
                node_type=self.type,
                node_id=self.node_id
            )
        else:
            raise ValueError(f"Invalid server type: {self.server_type}")

        await self.server.launch_server()

    async def unregister_node(self):
        """Unregister the node from the hub - only HTTP server does this"""
        if self.server_type == "http":
            try:
                logger.info("Unregistering node from hub")
                node_id = self.node_config["id"] if isinstance(self.node_config, dict) else self.node_config.id

                async with Hub() as hub:
                    success, user, user_id = await hub.signin(
                        os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                    )
                    success = await hub.delete_node(node_id=node_id)

                if success:
                    logger.info("Successfully unregistered node")
                else:
                    logger.error("Failed to unregister node")
                    raise Exception("Failed to unregister node")
            except Exception as e:
                logger.error(f"Error during node unregistration: {e}")
                raise

    async def graceful_shutdown(self, sig=None):
        """Handle graceful shutdown of the server"""
        if sig:
            logger.info(f'Received exit signal {sig.name}...')
        
        logger.info("Initiating graceful shutdown...")
        self.shutdown_event.set()
        
        try:
            if isinstance(self.server, GrpcServer):
                await self.server.graceful_shutdown(timeout=10.0)
            elif isinstance(self.server, WebSocketServer):
                if hasattr(self.server, 'graceful_shutdown'):
                    await self.server.graceful_shutdown()
                else:
                    self.server.manager.active_connections.clear()
            
            # Only HTTP server handles node registration
            await self.unregister_node()
            logger.info("Graceful shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
        finally:
            logger.info("Forcing exit...")
            os._exit(0)

async def run_server(server_type: str, port: int):
    """Main function to run a single server"""
    node_server = NodeServer(server_type, port)
    
    def signal_handler(sig):
        """Handle shutdown signals"""
        asyncio.create_task(node_server.graceful_shutdown(sig))

    try:
        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig, 
                lambda s=sig: signal_handler(s)
            )

        # Register node (only for HTTP server)
        await node_server.register_node()
        
        # Start server
        await node_server.start_server()
        
        # Wait for shutdown event
        await node_server.shutdown_event.wait()
        
    except Exception as e:
        logger.error(f"Error running server: {e}")
        await node_server.graceful_shutdown()
    finally:
        if not node_server.shutdown_event.is_set():
            await node_server.graceful_shutdown()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run node server")
    parser.add_argument(
        "--server-type",
        type=str,
        choices=["http", "ws", "grpc"],
        required=True,
        help="Type of server to run"
    )
    parser.add_argument(
        "--port",
        type=int,
        required=True,
        help="Port to run the server on"
    )
    
    args = parser.parse_args()

    asyncio.run(run_server(
        server_type=args.server_type,
        port=args.port
    ))