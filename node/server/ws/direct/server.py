import json
import uvicorn
import asyncio
from typing import Dict
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

from node.utils import get_logger
from node.storage.hub.hub import Hub
from node.storage.db.db import DB
from naptha_sdk.schemas import DockerParams, ModuleRunInput
from node.worker.docker_worker import execute_docker_module
from node.worker.template_worker import run_flow
from node.user import check_user, register_user
import os
from datetime import datetime

logger = get_logger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

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
                result = await self.create_task(data)
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
                result = await self.check_user_ws_direct(data)
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
                result = await self.register_user_ws_direct(data)
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

    async def create_task(self, data: str) -> str:
        try:
            job = json.loads(data)
            logger.info(f"Processing job: {job}")

            module_run_input = ModuleRunInput(**job)

            async with Hub() as hub:
                success, user, user_id = await hub.signin(os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD"))
                module = await hub.list_modules(f"module:{module_run_input.module_name}")
                
                if not module:
                    return json.dumps({"status": "error", "message": "Module not found"})
                
                module_run_input.module_type = module["type"]
                module_run_input.module_version = module["version"]
                module_run_input.module_url = module["url"]
                
                if module["type"] == "docker":
                    module_run_input.module_params = DockerParams(**module_run_input.module_params)

            async with DB() as db:
                module_run = await db.create_module_run(module_run_input)
                logger.info("Created module run")

            # Execute the task
            if module_run.module_type in ["flow", "template"]:
                task = run_flow.delay(module_run.dict())
            elif module_run.module_type == "docker":
                task = execute_docker_module.delay(module_run.dict())
            else:
                return json.dumps({"status": "error", "message": "Invalid module type"})

            # Wait for the task to complete
            while not task.ready():
                await asyncio.sleep(1)

            # Retrieve the updated module run from the database
            async with DB() as db:
                updated_module_run = await db.list_module_runs(module_run.id)
                
            if updated_module_run:
                # Convert the Pydantic model to a dictionary with datetime objects serialized
                updated_module_run_dict = updated_module_run.dict()
            
                return json.dumps({"status": "success", "data": updated_module_run_dict}, cls=DateTimeEncoder)
            else:
                return json.dumps({"status": "error", "message": "Failed to retrieve updated module run"})

        except Exception as e:
            logger.error(f"Error processing job: {str(e)}")
            return json.dumps({"status": "error", "message": str(e)})

    async def check_user_ws_direct(self, data: str):
        data = json.loads(data)
        response = await check_user(data)
        return json.dumps(response)

    async def register_user_ws_direct(self, data: str):
        data = json.loads(data)
        response = await register_user(data)
        return json.dumps(response)