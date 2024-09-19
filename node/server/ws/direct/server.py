import json
import uvicorn
import asyncio
from typing import Dict
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

from node.utils import get_logger
from node.server.ws.direct.task import create_task
from node.server.ws.direct.user import check_user_ws_direct, register_user_ws_direct

logger = get_logger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str, task: str):
        await websocket.accept()
        self.active_connections[f"{client_id}_{task}"] = websocket

    def disconnect(self, client_id: str, task: str):
        key = f"{client_id}_{task}"
        if key in self.active_connections:
            del self.active_connections[key]

    async def send_message(self, message: str, client_id: str, task: str):
        key = f"{client_id}_{task}"
        if key in self.active_connections:
            try:
                await self.active_connections[key].send_text(message)
            except (ConnectionClosedOK, ConnectionClosedError, WebSocketDisconnect) as e:
                logger.warning(f"Connection closed while sending message to client {client_id} for task {task}: {str(e)}")
                self.disconnect(client_id, task)
            except Exception as e:
                logger.error(f"Error sending message to client {client_id} for task {task}: {str(e)}")


class WebSocketDirectServer:
    def __init__(self, host: str, port: int):
        self.host = host
        if 'http' in host:
            self.host = host.split('http://')[1]
        self.port = port
        self.app = FastAPI()
        self.manager = ConnectionManager()

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Add the WebSocket route
        self.app.add_api_websocket_route("/ws/{client_id}/create_task", self.create_task_endpoint)
        self.app.add_api_websocket_route("/ws/{client_id}/check_user", self.check_user_endpoint)
        self.app.add_api_websocket_route("/ws/{client_id}/register_user", self.register_user_endpoint)

    async def create_task_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "create_task")
        try:
            while True:
                data = await websocket.receive_text()
                logger.info(f"Endpoint: create_task :: Received data: {data}")
                result = await create_task(data)
                logger.info(f"Endpoint: create_task :: Sending result: {result}")
                await self.manager.send_message(result, client_id, "create_task")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "create_task")
        except Exception as e:
            logger.error(f"Error in WebSocket connection for client {client_id} in create_task: {str(e)}")
            self.manager.disconnect(client_id, "create_task")

    async def check_user_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "check_user")
        try:
            while True:
                data = await websocket.receive_text()
                logger.info(f"Endpoint: check_user :: Received data: {data}")
                result = await check_user_ws_direct(data)
                logger.info(f"Endpoint: check_user :: Sending result: {result}")
                await self.manager.send_message(result, client_id, "check_user")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "check_user")

    async def register_user_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "register_user")   
        try:
            while True:
                data = await websocket.receive_text()
                logger.info(f"Endpoint: register_user :: Received data: {data}")
                result = await register_user_ws_direct(data)
                logger.info(f"Endpoint: register_user :: Sending result: {result}")
                await self.manager.send_message(result, client_id, "register_user")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "register_user")

    async def launch_server(self):
        logger.info(f"Launching WebSocket server...")
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="debug",
            timeout_keep_alive=300,
            limit_concurrency=200,
            backlog=4096,
            reload=True
        )
        server = uvicorn.Server(config)
        await server.serve()