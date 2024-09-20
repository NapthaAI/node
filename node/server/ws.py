import asyncio
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
from naptha_sdk.schemas import DockerParams, ModuleRun, ModuleRunInput
from node.storage.db.db import DB
from node.storage.hub.hub import Hub
from node.user import check_user, register_user
from node.utils import get_logger
from node.worker.docker_worker import execute_docker_module
from node.worker.template_worker import run_flow
import os
import traceback
from typing import Dict
import uvicorn
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

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


class WebSocketServer:
    def __init__(self, host: str, port: int, node_type: str):
        self.host = host
        if 'http' in host:
            self.host = host.split('http://')[1]
        self.port = port
        self.app = FastAPI()
        self.manager = ConnectionManager()
        self.node_type = node_type

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
                if self.node_type == "direct":
                    result = await self.create_task_direct(data)
                else:
                    result = await self.create_task_indirect(websocket, data, client_id)
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
                if self.node_type == "direct":
                    result = await self.check_user_direct(data)
                else:
                    result = await self.check_user_indirect(data, client_id)
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
                if self.node_type == "direct":
                    result = await self.register_user_direct(data)
                else:
                    result = await self.register_user_indirect(data, client_id)
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

    async def create_task_direct(self, data: str) -> str:
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

    async def create_task_indirect(self, message: dict, client_id: str) -> ModuleRun:
        """
        Create a task and return the task
        """
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            module_run_input = ModuleRunInput(**params)
            logger.info(f"Received task: {module_run_input}")

            async with Hub() as hub:
                success, user, user_id = await hub.signin(os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD"))
                module = await hub.list_modules(f"module:{module_run_input.module_name}")
                logger.info(f"Found module: {module}")

                if not module:
                    raise HTTPException(status_code=404, detail="Module not found")

                module_run_input.module_type = module["type"]
                module_run_input.module_version = module["version"]
                module_run_input.module_url = module["url"]

                if module["type"] == "docker":
                    module_run_input.module_params = DockerParams(**module_run_input.module_params)

            async with DB() as db:
                module_run = await db.create_module_run(module_run_input)
                logger.info("Created module run")

                updated_module_run = await db.update_module_run(module_run.id, module_run)
                logger.info("Updated module run")

            # Enqueue the module run in Celery
            if module_run.module_type in ["flow", "template"]:
                run_flow.delay(module_run.dict())
            elif module_run.module_type == "docker":
                execute_docker_module.delay(module_run.dict())
            else:
                raise HTTPException(status_code=400, detail="Invalid module type")

            response['params'] = module_run.model_dict()
            await self.manager.send_message(json.dumps(response), client_id, "create_task")
            return module_run

        except Exception as e:
            logger.error(f"Failed to run module: {str(e)}")
            error_details = traceback.format_exc()
            logger.error(f"Full traceback: {error_details}")
            response['params'] = {'error': f"Failed to run module: {str(e)}"}
            await self.manager.send_message(json.dumps(response), client_id, "create_task")
            raise HTTPException(status_code=500, detail=f"Failed to run module: {module_run_input}")

    async def check_user_direct(self, data: str):
        data = json.loads(data)
        response = await check_user(data)
        return json.dumps(response)

    async def check_user_indirect(self, message: Dict, client_id: str) -> Dict:
        """Check if a user exists"""
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            result = await check_user(params)
            response['params'] = result
            await self.manager.send_message(json.dumps(response), client_id, "check_user")
        except Exception as e:
            response['params'] = {'error': str(e)}
            await self.manager.send_message(json.dumps(response), client_id, "check_user")

    async def register_user_direct(self, data: str):
        data = json.loads(data)
        response = await register_user(data)
        return json.dumps(response)
    
    async def register_user_indirect(self, message: Dict, client_id: str) -> Dict:
        """Register a user"""
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            result = await register_user(params)
            response['params'] = result
            await self.manager.send_message(json.dumps(response), client_id, "register_user")
        except Exception as e:
            logger.error(f"Error registering user: {e}")
            response['params'] = {'error': str(e)}
            await self.manager.send_message(json.dumps(response), client_id, "register_user")