import asyncio
import json
import websockets

from node.comms.ws_server.task import create_task_ws, check_task_ws
from node.comms.ws_server.user import register_user_ws, check_user_ws
from node.comms.ws_server.orchestration import create_task_run_ws, update_task_run_ws
from node.comms.ws_server.storage import write_to_ipfs_ws, read_from_ipfs_or_ipns, write_storage_ws, read_storage_ws
from node.utils import get_logger


logger = get_logger(__name__)

class WebSocketServer:
    def __init__(self, uri: str):
        self.uri = uri

    async def websocket_handler(self):
        """Handles persistent WebSocket connection."""
        async with websockets.connect(self.uri, ping_interval=None) as websocket:
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
                            await read_from_ipfs_or_ipns(
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

    def launch_server(self):
        logger.info(f"Launching WebSocket server on {self.uri}")
        asyncio.run(self.websocket_handler())