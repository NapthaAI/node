import os
import json
import base64
import asyncio
import uvicorn
import websockets
from datetime import datetime
import traceback
import logging
from typing import Dict
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from node.schemas import (
    AgentRun, 
    AgentRunInput, 
    OrchestratorRun, 
    OrchestratorRunInput
)
from node.config import BASE_OUTPUT_DIR
from node.storage.db.db import DB
from node.storage.hub.hub import Hub
from node.storage.storage import (
    write_to_ipfs,
    read_from_ipfs_or_ipns,
    write_storage,
    read_storage,
    publish_to_ipns_func,
    update_ipns_record,
)
from node.user import register_user, check_user
from node.worker.docker_worker import execute_docker_agent
from node.worker.template_worker import run_orchestrator, run_agent


logger = logging.getLogger(__name__)
CHUNK_SIZE = 256 * 1024


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, client_id: str, task: str):
        await websocket.accept()
        if client_id not in self.active_connections:
            self.active_connections[client_id] = {}
        self.active_connections[client_id][task] = websocket
        logger.info(f"WebSocket connection established for {client_id}_{task}")

    def disconnect(self, client_id: str, task: str):
        if (
            client_id in self.active_connections
            and task in self.active_connections[client_id]
        ):
            del self.active_connections[client_id][task]
            if not self.active_connections[client_id]:
                del self.active_connections[client_id]
            logger.info(f"WebSocket connection closed for {client_id}_{task}")

    async def send_message(self, message: str, client_id: str, task: str):
        if (
            client_id in self.active_connections
            and task in self.active_connections[client_id]
        ):
            try:
                await self.active_connections[client_id][task].send_text(message)
                logger.info(f"Sent message to {client_id}_{task}")
            except Exception as e:
                logger.error(f"Error sending message to {client_id}_{task}: {str(e)}")
                self.disconnect(client_id, task)


class TransientDatabaseError(Exception):
    pass


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class WebSocketServer:
    def __init__(self, host: str, port: int, node_id: str):
        self.host = host
        self.port = port
        self.node_id = node_id
        self.app = FastAPI()
        self.temp_files = {}
        self.manager = ConnectionManager()
        self.server = None
        self._started = False

        # Add shutdown event handler
        @self.app.on_event("shutdown")
        async def shutdown_event():
            logger.info("Received shutdown signal from FastAPI")
            try:
                await self.graceful_shutdown()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        # Add health check endpoint
        @self.app.get("/health")
        async def health_check():
            """Simple health check endpoint"""
            return {"status": "ok", "server_type": "websocket"}
        
        self.app.add_api_websocket_route(
            "/ws/run_agent/{client_id}", self.run_agent_endpoint
        )
        self.app.add_api_websocket_route(
            "/ws/check_agent_run/{client_id}", self.check_agent_run_endpoint
        )
        self.app.add_api_websocket_route(
            "/ws/run_orchestrator/{client_id}", 
            self.run_orchestrator_endpoint
        )
        # self.app.add_api_websocket_route(
        #     "/ws/check_orchestrator_run/{client_id}", 
        #     self.check_orchestrator_run_endpoint
        # )
        self.app.add_api_websocket_route(
            "/ws/check_user/{client_id}", self.check_user_endpoint
        )
        self.app.add_api_websocket_route(
            "/ws/register_user/{client_id}", self.register_user_endpoint
        )
        self.app.add_api_websocket_route(
            "/ws/write_storage/{client_id}", self.write_storage_endpoint
        )
        self.app.add_api_websocket_route(
            "/ws/write_ipfs/{client_id}", self.write_ipfs_endpoint
        )
        self.app.add_api_websocket_route(
            "/ws/read_storage/{client_id}", self.read_storage_endpoint
        )
        self.app.add_api_websocket_route(
            "/ws/read_ipfs/{client_id}", self.read_ipfs_endpoint
        )

    async def run_agent_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "run_agent")
        try:
            while True:
                try:
                    data = await websocket.receive_json()  # Try receiving data
                    logger.info(f"Endpoint: run_agent :: Received data: {data}")

                    # Simulating a response process
                    result = await self.run_agent(data, client_id)
                    logger.info(f"Endpoint: run_agent :: Sending result: {result}")
                    await self.manager.send_message(result, client_id, "run_agent")

                except WebSocketDisconnect:
                    logger.warning(f"Client {client_id} disconnected.")
                    self.manager.disconnect(client_id, "run_agent")
                    break  # Exit the loop if client disconnects

                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    await self.manager.send_message(
                        json.dumps({"status": "error", "message": "Invalid JSON"}),
                        client_id,
                        "run_agent",
                    )

                except Exception as e:
                    logger.error(f"Error processing request: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    await self.manager.send_message(
                        json.dumps({"status": "error", "message": str(e)}),
                        client_id,
                        "run_agent",
                    )

        except WebSocketDisconnect:
            logger.warning(f"Client {client_id} disconnected (outer).")
            self.manager.disconnect(client_id, "run_agent")

    async def run_orchestrator_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "run_orchestrator")

        try:
            while True:
                data = await websocket.receive_json()
                logger.info(f"Endpoint: run_orchestrator :: Received data: {data}")

                result = await self.run_orchestrator(data, client_id)
                logger.info(f"Endpoint: run_orchestrator :: Sending result: {result}")
                await self.manager.send_message(result, client_id, "run_orchestrator")

        except WebSocketDisconnect:
            logger.warning(f"Client {client_id} disconnected (outer).")
            self.manager.disconnect(client_id, "run_orchestrator")

        except Exception as e:
            logger.error(f"Error in WebSocket connection for client {client_id} in run_orchestrator: {str(e)}")
            self.manager.disconnect(client_id, "run_orchestrator")

    async def establish_connection(self):
        while True:
            try:
                websocket = await websockets.connect(self.host)
                logger.info(f"Connected to relay server at {self.host}")
                return websocket
            except Exception as e:
                logger.error(f"Failed to connect to relay server: {e}")
                await asyncio.sleep(5)  # Wait before retrying

    async def send_response(self, response):
        try:
            await self.relay_websocket.send(json.dumps(response, cls=DateTimeEncoder))
            logger.info(f"Sent response: {response}")
        except Exception as e:
            logger.error(f"Error sending response: {str(e)}")
            # If the connection is closed, try to reconnect
            if isinstance(e, websockets.exceptions.ConnectionClosed):
                logger.info("Attempting to reconnect to relay server...")
                self.relay_websocket = await self.establish_connection()
                # Try sending the response again after reconnecting
                try:
                    await self.relay_websocket.send(
                        json.dumps(response, cls=DateTimeEncoder)
                    )
                    logger.info(f"Sent response after reconnection: {response}")
                except Exception as e2:
                    logger.error(
                        f"Failed to send response after reconnection: {str(e2)}"
                    )

    async def run_agent(self, data: dict, client_id: str) -> str:
        try:
            logger.info(f"run_agent: Received data: {data}")
            agent_run_input = AgentRunInput(**data)
            logger.info(f"run_agent: Created AgentRunInput: {agent_run_input}")
            result = await self.run_agent(agent_run_input)
            logger.info(f"run_agent: Got result: {result}")
            return json.dumps(
                {"status": "success", "data": result}, cls=DateTimeEncoder
            )
        except Exception as e:
            logger.error(f"Error processing job: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return json.dumps({"status": "error", "message": str(e)})

    async def run_orchestrator(self, data: dict, client_id: str) -> str:
        try:
            logger.info(f"run_orchestrator: Received data: {data}")
            orchestrator_run_input = OrchestratorRunInput(**data)
            logger.info(f"run_orchestrator: Created OrchestratorRunInput: {orchestrator_run_input}")
            result = await self.run_orchestrator(orchestrator_run_input)
            logger.info(f"run_orchestrator: Got result: {result}")
            return json.dumps(
                {"status": "success", "data": result}, cls=DateTimeEncoder
            )
        except Exception as e:
            logger.error(f"Error processing job: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return json.dumps({"status": "error", "message": str(e)})

    async def run_agent(self, agent_run_input: AgentRunInput) -> AgentRun:
        try:
            logger.info(f"Received task: {agent_run_input}")

            async with Hub() as hub:
                success, user, user_id = await hub.signin(
                    os.getenv("HUB_USERNAME"), 
                    os.getenv("HUB_PASSWORD")
                )
                agent_module = await hub.list_agents(f"{agent_run_input.agent_deployment.module['name']}")
                logger.info(f"Found agent: {agent_module}")

                if not agent_module:
                    raise ValueError("Agent not found")

                agent_run_input.agent_deployment.module = agent_module

            async with DB() as db:
                agent_run = await db.create_agent_run(agent_run_input)
                if not agent_run:
                    raise ValueError("Failed to create agent run")
                agent_run_data = agent_run.model_dump()

            # Execute the task
            if agent_run.agent_deployment.module["module_type"] == "package":
                task = run_agent.delay(agent_run_data)
            elif agent_run.agent_deployment.module["module_type"] == "docker":
                task = execute_docker_agent.delay(agent_run_data)
            else:
                raise HTTPException(status_code=400, detail="Invalid agent run type")

            # Wait for the task to complete
            while not task.ready():
                await asyncio.sleep(1)

            # Retrieve the updated run from the database
            async with DB() as db:
                updated_run = await db.list_agent_runs(agent_run_data['id'])
                if isinstance(updated_run, list):
                    updated_run = updated_run[0]
                    
            if isinstance(updated_run, dict):
                updated_run.pop("_sa_instance_state", None)
            else:
                updated_run = updated_run.__dict__
                updated_run.pop("_sa_instance_state", None)

            # Convert timestamps to strings if they exist
            if 'created_time' in updated_run and isinstance(updated_run['created_time'], datetime):
                updated_run['created_time'] = updated_run['created_time'].isoformat()
            if 'start_processing_time' in updated_run and isinstance(updated_run['start_processing_time'], datetime):
                updated_run['start_processing_time'] = updated_run['start_processing_time'].isoformat()
            if 'completed_time' in updated_run and isinstance(updated_run['completed_time'], datetime):
                updated_run['completed_time'] = updated_run['completed_time'].isoformat()

            
            return updated_run

        except Exception as e:
            logger.error(f"Failed to run module: {str(e)}")
            raise

    async def run_orchestrator(self, agent_run_input: AgentRunInput) -> AgentRun:
        try:
            logger.info(f"Received task: {agent_run_input}")

            async with Hub() as hub:
                success, user, user_id = await hub.signin(
                    os.getenv("HUB_USERNAME"), 
                    os.getenv("HUB_PASSWORD")
                )

                orchestrator_module = await hub.list_orchestrators(f"{agent_run_input.orchestrator_deployment.module['name']}")
                logger.info(f"Found orchestrator: {orchestrator_module}")

                if not orchestrator_module:
                    raise ValueError("Orchestrator not found")

                agent_run_input.orchestrator_deployment.module = orchestrator_module

            async with DB() as db:
                orchestrator_run = await db.create_orchestrator_run(agent_run_input)
                if not orchestrator_run:
                    raise ValueError("Failed to create orchestrator run")
                orchestrator_run_data = orchestrator_run.model_dump()

            if orchestrator_run.orchestrator_deployment.module["module_type"] == "package":
                task = run_orchestrator.delay(orchestrator_run_data)
            elif orchestrator_run.orchestrator_deployment.module["module_type"] == "docker":
                raise ValueError("Docker orchestrators are not supported")
            else:
                raise ValueError("Invalid module type")

            # Wait for the task to complete
            while not task.ready():
                await asyncio.sleep(1)

            async with DB() as db:
                updated_run = await db.list_orchestrator_runs(orchestrator_run_data['id'])
                if isinstance(updated_run, list):
                    updated_run = updated_run[0]
                if not isinstance(updated_run, dict):
                    updated_run = updated_run.__dict__
                updated_run.pop("_sa_instance_state", None)

            # Convert timestamps to strings if they exist
            for time_field in ['created_time', 'start_processing_time', 'completed_time']:
                if time_field in updated_run and isinstance(updated_run[time_field], datetime):
                    updated_run[time_field] = updated_run[time_field].isoformat()

            return updated_run

        except Exception as e:
            logger.error(f"Failed to run module: {str(e)}")
            raise

    async def check_agent_run_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "check_agent_run")
        try:
            while True:
                data = await websocket.receive_text()
                logger.info(f"Endpoint: check_agent_run :: Received data: {data}")
                result = await self.check_agent_run(data, client_id)
                logger.info(f"Endpoint: check_agent_run :: Sending result: {result}")
                await self.manager.send_message(result, client_id, "check_agent_run")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "check_agent_run")
        except Exception as e:
            logger.error(
                f"Error in WebSocket connection for client {client_id} in check_task: {str(e)}"
            )
            self.manager.disconnect(client_id, "check_agent_run")

    async def check_agent_run(self, data: str, client_id: str) -> str:
        try:
            agent_run_data = json.loads(data)
            agent_run = AgentRun(**agent_run_data)
            result = await self.check_agent_run(agent_run)
            return json.dumps(
                {"status": "success", "data": result.dict()}, cls=DateTimeEncoder
            )
        except Exception as e:
            logger.error(f"Error checking agent run: {str(e)}")
            return json.dumps({"status": "error", "message": str(e)})

    async def check_agent_run(self, agent_run: AgentRun) -> AgentRun:
        """
        Check an agent run
        :param agent_run: AgentRun details
        :return: Status
        """
        try:
            logger.info("Checking agent run")
            id_ = agent_run.id
            if id_ is None:
                raise HTTPException(status_code=400, detail="Agent run ID is required")
            async with DB() as db:
                agent_run = await db.list_agent_runs(id_)
            if not agent_run:
                raise HTTPException(status_code=404, detail="Agent run not found")
            status = agent_run.status
            logger.info(f"Found agent run status: {status}")
            if agent_run.status == "completed":
                logger.info(f"Task completed. Returning output: {agent_run.results}")
            elif agent_run.status == "error":
                logger.info(f"Task failed. Returning error: {agent_run.error_message}")
            logger.info(f"Response: {agent_run}")
            return agent_run
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to check task: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail="Internal server error occurred while checking task",
            )

    async def check_user_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "check_user")
        try:
            while True:
                data = await websocket.receive_text()
                result = await self.check_user(data)
                await self.manager.send_message(result, client_id, "check_user")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "check_user")

    async def check_user(self, data: str) -> str:
        data = json.loads(data)
        _, response = await check_user(data)
        if '_sa_instance_state' in response:
            response.pop('_sa_instance_state')
        return json.dumps(response)

    async def register_user_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "register_user")
        try:
            while True:
                data = await websocket.receive_text()
                result = await self.register_user(data)
                await self.manager.send_message(result, client_id, "register_user")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "register_user")

    async def register_user(self, data: str) -> str:
        data = json.loads(data)
        _, response = await register_user(data)
        if '_sa_instance_state' in response:
            response.pop('_sa_instance_state')
        return json.dumps(response)

    async def write_storage_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "write_storage")
        try:
            while True:
                data = await websocket.receive_text()
                result = await self.write_storage(data, client_id)
                await self.manager.send_message(result, client_id, "write_storage")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "write_storage")

    async def write_storage(self, data: str, client_id: str) -> str:
        params = json.loads(data)
        filename = params["filename"]
        file_data = params["file_data"]

        temp_dir = os.path.join(BASE_OUTPUT_DIR, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_filepath = os.path.join(temp_dir, f"{client_id}_{filename}.part")

        try:
            if file_data == "EOF":
                if temp_filepath in self.temp_files:
                    with open(self.temp_files[temp_filepath], "rb") as temp_file:
                        from fastapi import UploadFile

                        file = UploadFile(filename=filename, file=temp_file)
                        status_code, message_dict = await write_storage(file)
                    os.remove(self.temp_files[temp_filepath])
                    del self.temp_files[temp_filepath]
                    return json.dumps({"status": "success", "data": message_dict})
                else:
                    return json.dumps(
                        {"status": "error", "message": "File transfer not found"}
                    )
            else:
                chunk = base64.b64decode(file_data)
                if temp_filepath not in self.temp_files:
                    self.temp_files[temp_filepath] = temp_filepath
                with open(self.temp_files[temp_filepath], "ab") as temp_file:
                    temp_file.write(chunk)
                return json.dumps({"status": "success", "message": "Chunk received"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    async def write_ipfs_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "write_ipfs")
        try:
            while True:
                data = await websocket.receive_text()
                result = await self.write_ipfs(json.loads(data), client_id)
                await self.manager.send_message(
                    json.dumps(result), client_id, "write_ipfs"
                )
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "write_ipfs")
        except Exception as e:
            logger.error(f"Error in write_ipfs_endpoint: {str(e)}")
            await self.manager.send_message(
                json.dumps({"status": "error", "message": str(e)}),
                client_id,
                "write_ipfs",
            )

    async def write_ipfs(self, params: dict, client_id: str) -> dict:
        filename = params["filename"]
        file_data = params["file_data"]
        publish_to_ipns = params.get("publish_to_ipns", False)
        update_ipns_name = params.get("update_ipns_name")

        temp_dir = os.path.join(BASE_OUTPUT_DIR, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_filepath = os.path.join(temp_dir, f"{client_id}_{filename}.part")

        try:
            if file_data == "EOF":
                if temp_filepath in self.temp_files:
                    with open(self.temp_files[temp_filepath], "rb") as temp_file:
                        file = UploadFile(filename=filename, file=temp_file)
                        status_code, response = await write_to_ipfs(
                            file, publish_to_ipns, update_ipns_name
                        )
                    os.remove(self.temp_files[temp_filepath])
                    del self.temp_files[temp_filepath]

                    if status_code == 201:
                        ipfs_hash = response["ipfs_hash"]

                        if publish_to_ipns:
                            ipns_hash = publish_to_ipns_func(ipfs_hash)
                            response["ipns_hash"] = ipns_hash
                            response["message"] += " and published to IPNS"
                        elif update_ipns_name:
                            updated_ipns_hash = update_ipns_record(
                                update_ipns_name, ipfs_hash
                            )
                            response["ipns_hash"] = updated_ipns_hash
                            response["message"] += " and IPNS record updated"

                    return {"status": "success", "data": response}
                else:
                    return {"status": "error", "message": "File transfer not found"}
            else:
                chunk = base64.b64decode(file_data)
                if temp_filepath not in self.temp_files:
                    self.temp_files[temp_filepath] = temp_filepath
                with open(self.temp_files[temp_filepath], "ab") as temp_file:
                    temp_file.write(chunk)
                return {"status": "success", "message": "Chunk received"}
        except Exception as e:
            logger.error(f"Error in write_to_ipfs: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def read_storage_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "read_storage")
        try:
            while True:
                data = await websocket.receive_text()
                await self.read_storage(json.loads(data), client_id, websocket)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "read_storage")
        except Exception as e:
            logger.error(f"Error in read_storage_endpoint: {str(e)}")
            await self.manager.send_message(
                json.dumps({"status": "error", "message": str(e)}),
                client_id,
                "read_storage",
            )

    async def read_storage(self, params: dict, client_id: str, websocket: WebSocket):
        job_id = params["folder_id"]
        try:
            status_code, message_dict = await read_storage(job_id)
            if status_code == 200:
                zip_filename = message_dict["path"]
                file_size = os.path.getsize(zip_filename)
                chunk_index = 0
                chunk_total = (file_size // CHUNK_SIZE) + 1

                with open(zip_filename, "rb") as file:
                    while chunk := file.read(CHUNK_SIZE):
                        encoded_chunk = base64.b64encode(chunk).decode("utf-8")
                        response = {
                            "status": "success",
                            "data": {
                                "file_data": encoded_chunk,
                                "filename": os.path.basename(zip_filename),
                                "chunk_index": chunk_index,
                                "chunk_total": chunk_total,
                            },
                        }
                        await self.manager.send_message(
                            json.dumps(response), client_id, "read_storage"
                        )
                        chunk_index += 1

                # Send EOF
                response = {
                    "status": "success",
                    "data": {
                        "file_data": "EOF",
                        "filename": os.path.basename(zip_filename),
                        "chunk_index": chunk_index,
                        "chunk_total": chunk_total,
                    },
                }
                await self.manager.send_message(
                    json.dumps(response), client_id, "read_storage"
                )
            else:
                await self.manager.send_message(
                    json.dumps({"status": "error", "message": message_dict["message"]}),
                    client_id,
                    "read_storage",
                )
        except Exception as e:
            logger.error(f"Error in read_storage: {str(e)}")
            await self.manager.send_message(
                json.dumps({"status": "error", "message": str(e)}),
                client_id,
                "read_storage",
            )

    async def read_ipfs_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "read_ipfs")
        try:
            while True:
                data = await websocket.receive_text()
                await self.read_ipfs(json.loads(data), client_id, websocket)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "read_ipfs")
        except Exception as e:
            logger.error(f"Error in read_ipfs_endpoint: {str(e)}")
            await self.manager.send_message(
                json.dumps({"status": "error", "message": str(e)}),
                client_id,
                "read_ipfs",
            )

    async def read_ipfs(self, params: dict, client_id: str, websocket: WebSocket):
        hash_or_name = params["hash_or_name"]
        try:
            status_code, message_dict = await read_from_ipfs_or_ipns(hash_or_name)
            if status_code == 200:
                if "content" in message_dict:
                    # For zipped directory content
                    content = message_dict["content"]
                    file_size = len(content)
                    chunk_total = (file_size // CHUNK_SIZE) + 1
                    for chunk_index in range(chunk_total):
                        start = chunk_index * CHUNK_SIZE
                        end = start + CHUNK_SIZE
                        chunk = content[start:end]
                        encoded_chunk = base64.b64encode(chunk).decode("utf-8")
                        response = {
                            "status": "success",
                            "data": {
                                "file_data": encoded_chunk,
                                "filename": f"{hash_or_name}.zip",
                                "chunk_index": chunk_index,
                                "chunk_total": chunk_total,
                            },
                        }
                        await self.manager.send_message(
                            json.dumps(response), client_id, "read_ipfs"
                        )
                else:
                    # For single file content
                    temp_filename = message_dict["path"]
                    file_size = os.path.getsize(temp_filename)
                    chunk_total = (file_size // CHUNK_SIZE) + 1
                    with open(temp_filename, "rb") as file:
                        for chunk_index in range(chunk_total):
                            chunk = file.read(CHUNK_SIZE)
                            encoded_chunk = base64.b64encode(chunk).decode("utf-8")
                            response = {
                                "status": "success",
                                "data": {
                                    "file_data": encoded_chunk,
                                    "filename": message_dict["filename"],
                                    "chunk_index": chunk_index,
                                    "chunk_total": chunk_total,
                                },
                            }
                            await self.manager.send_message(
                                json.dumps(response), client_id, "read_ipfs"
                            )

                # Send EOF
                response = {
                    "status": "success",
                    "data": {
                        "file_data": "EOF",
                        "filename": message_dict.get("filename", f"{hash_or_name}.zip"),
                        "chunk_index": chunk_total - 1,
                        "chunk_total": chunk_total,
                    },
                }
                await self.manager.send_message(
                    json.dumps(response), client_id, "read_ipfs"
                )
            else:
                await self.manager.send_message(
                    json.dumps({"status": "error", "message": message_dict["message"]}),
                    client_id,
                    "read_ipfs",
                )
        except Exception as e:
            logger.error(f"Error in read_ipfs: {str(e)}")
            await self.manager.send_message(
                json.dumps({"status": "error", "message": str(e)}),
                client_id,
                "read_ipfs",
            )

    async def graceful_shutdown(self):
        """Fast and efficient WebSocket server shutdown"""
        try:
            logger.info("WebSocket server shutting down...")
            
            # 1. Close all active connections concurrently with timeout
            close_tasks = []
            for client_id in list(self.manager.active_connections.keys()):
                for task in list(self.manager.active_connections[client_id].keys()):
                    websocket = self.manager.active_connections[client_id][task]
                    close_tasks.append(
                        asyncio.create_task(websocket.close())
                    )
                    self.manager.disconnect(client_id, task)
                    
            if close_tasks:
                try:
                    # 2. Wait max 2 seconds for connections to close
                    await asyncio.wait_for(
                        asyncio.gather(*close_tasks, return_exceptions=True),
                        timeout=2.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Some connections failed to close gracefully")

            # 3. Stop server quickly
            if self.server and self._started:
                try:
                    await asyncio.wait_for(self.server.shutdown(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("Server shutdown timed out")
                finally:
                    self._started = False

            # 4. Clean up temp files without waiting
            if self.temp_files:
                for filepath in list(self.temp_files.values()):
                    try:
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    except Exception as e:
                        logger.error(f"Failed to remove temp file {filepath}: {e}")
                self.temp_files.clear()

        except Exception as e:
            logger.error(f"Error during WebSocket shutdown: {e}")
        finally:
            logger.info("WebSocket server shutdown complete")

    async def launch_server(self):
        """Start the WebSocket server"""
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="debug",
            timeout_keep_alive=300,
            limit_concurrency=2000,
            backlog=4096,
            timeout_graceful_shutdown=5,
            reload=False
        )
        self.server = uvicorn.Server(config)
        self._started = True
        try:
            await self.server.serve()
        finally:
            self._started = False
