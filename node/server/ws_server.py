import os
import json
import base64
import asyncio
import uvicorn
from datetime import datetime
import traceback
from typing import Dict
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

from node.schemas import AgentRun, AgentRunInput, DockerParams
from node.config import BASE_OUTPUT_DIR
from node.utils import get_logger
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
from node.worker.template_worker import run_flow


logger = get_logger(__name__)
CHUNK_SIZE = 256 * 1024


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str, task: str):
        await websocket.accept()
        key = f"{client_id}_{task}"
        self.active_connections[key] = websocket
        logger.info(f"WebSocket connection established for {key}")

    def disconnect(self, client_id: str, task: str):
        key = f"{client_id}_{task}"
        if key in self.active_connections:
            del self.active_connections[key]
            logger.info(f"WebSocket connection closed for {key}")

    async def send_message(self, message: str, client_id: str, task: str):
        key = f"{client_id}_{task}"
        if key in self.active_connections:
            try:
                logger.info(f"Sending message to {key}: {message}")
                await self.active_connections[key].send_text(message)
            except (ConnectionClosedOK, ConnectionClosedError, WebSocketDisconnect) as e:
                logger.warning(f"Connection closed while sending message to {key}: {str(e)}")
                self.disconnect(client_id, task)
            except Exception as e:
                logger.error(f"Error sending message to {key}: {str(e)}")


class TransientDatabaseError(Exception):
    pass

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class WebSocketServer:
    def __init__(self, host: str, port: int, node_type: str):
        self.host = host
        self.port = port
        self.node_type = node_type
        self.app = FastAPI()
        self.temp_files = {}
        self.manager = ConnectionManager()

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # run_agent
        self.app.add_api_websocket_route("/ws/run_agent/{client_id}", self.run_agent_endpoint)
        self.app.add_api_websocket_route("/ws/run_agent_indirect/{client_id}", self.run_agent_indirect_endpoint)

        # check_task
        self.app.add_api_websocket_route("/ws/check_agent_run/{client_id}", self.check_agent_run_endpoint)
        self.app.add_api_websocket_route("/ws/check_agent_run_indirect/{client_id}", self.check_agent_run_indirect_endpoint)

        # check_user
        self.app.add_api_websocket_route("/ws/check_user/{client_id}", self.check_user_endpoint)
        self.app.add_api_websocket_route("/ws/check_user_indirect/{client_id}", self.check_user_indirect_endpoint)

        # register_user
        self.app.add_api_websocket_route("/ws/register_user/{client_id}", self.register_user_endpoint)
        self.app.add_api_websocket_route("/ws/register_user_indirect/{client_id}", self.register_user_indirect_endpoint)
        
        # write_storage
        self.app.add_api_websocket_route("/ws/write_storage/{client_id}", self.write_storage_endpoint)
        self.app.add_api_websocket_route("/ws/write_storage_indirect/{client_id}", self.write_storage_indirect_endpoint)

        # write_to_ipfs
        self.app.add_api_websocket_route("/ws/write_ipfs/{client_id}", self.write_ipfs_endpoint)
        self.app.add_api_websocket_route("/ws/write_ipfs_indirect/{client_id}", self.write_ipfs_indirect_endpoint)

        # read_storage
        self.app.add_api_websocket_route("/ws/read_storage/{client_id}", self.read_storage_endpoint)
        self.app.add_api_websocket_route("/ws/read_storage_indirect/{client_id}", self.read_storage_indirect_endpoint)

        # read_from_ipfs
        self.app.add_api_websocket_route("/ws/read_ipfs/{client_id}", self.read_ipfs_endpoint)
        self.app.add_api_websocket_route("/ws/read_ipfs_indirect/{client_id}", self.read_ipfs_indirect_endpoint)

        # register_agent_run
        # self.app.add_api_websocket_route("/ws/register_agent_run/{client_id}", self.register_agent_run_endpoint)
        # self.app.add_api_websocket_route("/ws/register_agent_run_indirect/{client_id}", self.register_agent_run_indirect_endpoint)

        # update_agent_run
        # self.app.add_api_websocket_route("/ws/update_agent_run/{client_id}", self.update_agent_run_endpoint)
        # self.app.add_api_websocket_route("/ws/update_agent_run_indirect/{client_id}", self.update_agent_run_indirect_endpoint)    

    async def run_agent_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "run_agent")
        try:
            while True:
                try:
                    data = await websocket.receive_json()  # Try receiving data
                    logger.info(f"Endpoint: run_agent :: Received data: {data}")
                    
                    # Simulating a response process
                    result = await self.run_agent_direct(data, client_id)
                    logger.info(f"Endpoint: run_agent :: Sending result: {result}")
                    await self.manager.send_message(result, client_id, "run_agent")

                except WebSocketDisconnect:
                    logger.warning(f"Client {client_id} disconnected.")
                    self.manager.disconnect(client_id, "run_agent")
                    break  # Exit the loop if client disconnects

                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    await self.manager.send_message(json.dumps({"status": "error", "message": "Invalid JSON"}), client_id, "run_agent")

                except Exception as e:
                    logger.error(f"Error processing request: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    await self.manager.send_message(json.dumps({"status": "error", "message": str(e)}), client_id, "run_agent")

        except WebSocketDisconnect:
            logger.warning(f"Client {client_id} disconnected (outer).")
            self.manager.disconnect(client_id, "run_agent")

    async def run_agent_indirect_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "run_agent_indirect")
        try:
            while True:
                message = await websocket.receive_json()
                result = await self.run_agent_indirect(message, client_id)
                await self.manager.send_message(result, client_id, "run_agent_indirect")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "run_agent_indirect")

    async def run_agent_direct(self, data: dict, client_id: str) -> str:
        try:
            logger.info(f"run_agent_direct: Received data: {data}")
            agent_run_input = AgentRunInput(**data)
            logger.info(f"run_agent_direct: Created AgentRunInput: {agent_run_input}")
            result = await self.run_agent(agent_run_input)
            logger.info(f"run_agent_direct: Got result: {result}")
            return json.dumps({"status": "success", "data": result.dict()}, cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Error processing job: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return json.dumps({"status": "error", "message": str(e)})

    async def run_agent_indirect(self, message: dict, client_id: str) -> str:
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            agent_run_input = AgentRunInput(**params)
            result = await self.run_agent(agent_run_input)
            response['params'] = result.dict()
        except Exception as e:
            response['params'] = {'error': str(e)}
        return json.dumps(response)

    async def run_agent(self, agent_run_input: AgentRunInput) -> AgentRun:
        try:
            logger.info(f"Received task: {agent_run_input}")

            async with Hub() as hub:
                success, user, user_id = await hub.signin(os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD"))
                agent = await hub.list_agents(f"agent:{agent_run_input.agent_name}")
                logger.info(f"Found agent: {agent}")

                if not agent:
                    raise ValueError("Agent not found")

                agent_run_input.agent_run_type = agent["type"]
                agent_run_input.agent_version = agent["version"]
                agent_run_input.agent_source_url = agent["url"]

                if agent["type"] == "docker":
                    agent_run_input.agent_run_params = DockerParams(**agent_run_input.agent_run_params)

            async with DB() as db:
                agent_run = await db.create_agent_run(agent_run_input)
                logger.info("Created agent run")

            # Execute the task
            if agent_run.agent_run_type == "package":
                task = run_flow.delay(agent_run.dict())
            elif agent_run.agent_run_type == "docker":
                task = execute_docker_agent.delay(agent_run.dict())
            else:
                raise ValueError("Invalid module type")

            # Wait for the task to complete
            while not task.ready():
                await asyncio.sleep(1)

            # Retrieve the updated module run from the database
            async with DB() as db:
                updated_agent_run = await db.list_agent_runs(agent_run.id)
            
            return updated_agent_run

        except Exception as e:
            logger.error(f"Failed to run module: {str(e)}")
            raise

    async def check_agent_run_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "check_agent_run")
        try:
            while True:
                data = await websocket.receive_text()
                logger.info(f"Endpoint: check_agent_run :: Received data: {data}")
                result = await self.check_agent_run_direct(data, client_id)
                logger.info(f"Endpoint: check_agent_run :: Sending result: {result}")
                await self.manager.send_message(result, client_id, "check_agent_run")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "check_agent_run")
        except Exception as e:
            logger.error(f"Error in WebSocket connection for client {client_id} in check_task: {str(e)}")
            self.manager.disconnect(client_id, "check_agent_run")

    async def check_agent_run_indirect_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "check_agent_run_indirect")
        try:
            while True:
                message = await websocket.receive_json()
                result = await self.check_agent_run_indirect(message, client_id)
                await self.manager.send_message(result, client_id, "check_agent_run_indirect")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "check_agent_run_indirect")

    async def check_agent_run_direct(self, data: str, client_id: str) -> str:
        try:
            agent_run_data = json.loads(data)
            agent_run = AgentRun(**agent_run_data)
            result = await self.check_agent_run(agent_run)
            return json.dumps({"status": "success", "data": result.dict()}, cls=DateTimeEncoder)
        except Exception as e:
            logger.error(f"Error checking agent run: {str(e)}")
            return json.dumps({"status": "error", "message": str(e)})

    async def check_agent_run_indirect(self, message: dict, client_id: str) -> str:
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            agent_run = AgentRun(**params)
            result = await self.check_agent_run(agent_run)
            response['params'] = result.dict()
        except Exception as e:
            response['params'] = {'error': str(e)}
        return json.dumps(response)

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
            raise HTTPException(status_code=500, detail="Internal server error occurred while checking task")

    async def check_user_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "check_user")
        try:
            while True:
                data = await websocket.receive_text()
                result = await self.check_user_direct(data)
                await self.manager.send_message(result, client_id, "check_user")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "check_user")

    async def check_user_indirect_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "check_user_indirect")
        try:
            while True:
                message = await websocket.receive_json()
                result = await self.check_user_indirect(message, client_id)
                await self.manager.send_message(result, client_id, "check_user_indirect")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "check_user_indirect")

    async def check_user_direct(self, data: str) -> str:
        data = json.loads(data)
        response = await check_user(data)
        return json.dumps(response)

    async def check_user_indirect(self, message: dict, client_id: str) -> str:
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
        except Exception as e:
            response['params'] = {'error': str(e)}
        return json.dumps(response)

    async def register_user_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "register_user")
        try:
            while True:
                data = await websocket.receive_text()
                result = await self.register_user_direct(data)
                await self.manager.send_message(result, client_id, "register_user")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "register_user")

    async def register_user_indirect_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "register_user_indirect")
        try:
            while True:
                message = await websocket.receive_json()
                result = await self.register_user_indirect(message, client_id)
                await self.manager.send_message(result, client_id, "register_user_indirect")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "register_user_indirect")

    async def register_user_direct(self, data: str) -> str:
        data = json.loads(data)
        response = await register_user(data)
        return json.dumps(response)

    async def register_user_indirect(self, message: dict, client_id: str) -> str:
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
        except Exception as e:
            logger.error(f"Error registering user: {e}")
            response['params'] = {'error': str(e)}
        return json.dumps(response)

    async def write_storage_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "write_storage")
        try:
            while True:
                data = await websocket.receive_text()
                result = await self.write_storage_direct(data, client_id)
                await self.manager.send_message(result, client_id, "write_storage")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "write_storage")

    async def write_storage_indirect_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "write_storage_indirect")
        try:
            while True:
                message = await websocket.receive_json()
                result = await self.write_storage_indirect(message, client_id)
                await self.manager.send_message(result, client_id, "write_storage_indirect")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "write_storage_indirect")

    async def write_storage_direct(self, data: str, client_id: str) -> str:
        params = json.loads(data)
        filename = params['filename']
        file_data = params['file_data']
        
        temp_dir = os.path.join(BASE_OUTPUT_DIR, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_filepath = os.path.join(temp_dir, f"{client_id}_{filename}.part")

        try:
            if file_data == 'EOF':
                if temp_filepath in self.temp_files:
                    with open(self.temp_files[temp_filepath], "rb") as temp_file:
                        from fastapi import UploadFile
                        file = UploadFile(filename=filename, file=temp_file)
                        status_code, message_dict = await write_storage(file)
                    os.remove(self.temp_files[temp_filepath])
                    del self.temp_files[temp_filepath]
                    return json.dumps({"status": "success", "data": message_dict})
                else:
                    return json.dumps({"status": "error", "message": "File transfer not found"})
            else:
                chunk = base64.b64decode(file_data)
                if temp_filepath not in self.temp_files:
                    self.temp_files[temp_filepath] = temp_filepath
                with open(self.temp_files[temp_filepath], "ab") as temp_file:
                    temp_file.write(chunk)
                return json.dumps({"status": "success", "message": "Chunk received"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    async def write_storage_indirect(self, message: dict, client_id: str) -> str:
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            result = await self.write_storage_direct(json.dumps(params), client_id)
            response['params'] = json.loads(result)
        except Exception as e:
            response['params'] = {'error': str(e)}
        return json.dumps(response)
    
    async def write_ipfs_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "write_ipfs")
        try:
            while True:
                data = await websocket.receive_text()
                result = await self.write_ipfs(json.loads(data), client_id)
                await self.manager.send_message(json.dumps(result), client_id, "write_ipfs")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "write_ipfs")
        except Exception as e:
            logger.error(f"Error in write_ipfs_endpoint: {str(e)}")
            await self.manager.send_message(json.dumps({"status": "error", "message": str(e)}), client_id, "write_ipfs")

    async def write_ipfs_indirect_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "write_ipfs_indirect")
        try:
            while True:
                message = await websocket.receive_json()
                result = await self.write_ipfs_indirect(message, client_id)
                await self.manager.send_message(json.dumps(result), client_id, "write_ipfs_indirect")
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "write_ipfs_indirect")
        except Exception as e:
            logger.error(f"Error in write_ipfs_indirect_endpoint: {str(e)}")
            await self.manager.send_message(json.dumps({"status": "error", "message": str(e)}), client_id, "write_ipfs_indirect")

    async def write_ipfs(self, params: dict, client_id: str) -> dict:
        filename = params['filename']
        file_data = params['file_data']
        publish_to_ipns = params.get('publish_to_ipns', False)
        update_ipns_name = params.get('update_ipns_name')
        
        temp_dir = os.path.join(BASE_OUTPUT_DIR, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_filepath = os.path.join(temp_dir, f"{client_id}_{filename}.part")

        try:
            if file_data == 'EOF':
                if temp_filepath in self.temp_files:
                    with open(self.temp_files[temp_filepath], "rb") as temp_file:
                        file = UploadFile(filename=filename, file=temp_file)
                        status_code, response = await write_to_ipfs(file, publish_to_ipns, update_ipns_name)
                    os.remove(self.temp_files[temp_filepath])
                    del self.temp_files[temp_filepath]
                    
                    if status_code == 201:
                        ipfs_hash = response["ipfs_hash"]
                        
                        if publish_to_ipns:
                            ipns_hash = publish_to_ipns_func(ipfs_hash)
                            response["ipns_hash"] = ipns_hash
                            response["message"] += " and published to IPNS"
                        elif update_ipns_name:
                            updated_ipns_hash = update_ipns_record(update_ipns_name, ipfs_hash)
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

    async def write_ipfs_indirect(self, message: dict, client_id: str) -> dict:
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            result = await self.write_ipfs(params, client_id)
            response['params'] = result
        except Exception as e:
            logger.error(f"Error in write_ipfs_indirect: {str(e)}")
            response['params'] = {'status': 'error', 'message': str(e)}
        return response

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
            await self.manager.send_message(json.dumps({"status": "error", "message": str(e)}), client_id, "read_storage")

    async def read_storage_indirect_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "read_storage_indirect")
        try:
            while True:
                message = await websocket.receive_json()
                await self.read_storage_indirect(message, client_id, websocket)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "read_storage_indirect")
        except Exception as e:
            logger.error(f"Error in read_storage_indirect_endpoint: {str(e)}")
            await self.manager.send_message(json.dumps({"status": "error", "message": str(e)}), client_id, "read_storage_indirect")

    async def read_storage(self, params: dict, client_id: str, websocket: WebSocket):
        job_id = params['folder_id']
        try:
            status_code, message_dict = await read_storage(job_id)
            if status_code == 200:
                zip_filename = message_dict["path"]
                file_size = os.path.getsize(zip_filename)
                chunk_index = 0
                chunk_total = (file_size // CHUNK_SIZE) + 1

                with open(zip_filename, "rb") as file:
                    while chunk := file.read(CHUNK_SIZE):
                        encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                        response = {
                            "status": "success",
                            "data": {
                                'file_data': encoded_chunk,
                                'filename': os.path.basename(zip_filename),
                                'chunk_index': chunk_index,
                                'chunk_total': chunk_total
                            }
                        }
                        await self.manager.send_message(json.dumps(response), client_id, "read_storage")
                        chunk_index += 1

                # Send EOF
                response = {
                    "status": "success",
                    "data": {
                        'file_data': 'EOF',
                        'filename': os.path.basename(zip_filename),
                        'chunk_index': chunk_index,
                        'chunk_total': chunk_total
                    }
                }
                await self.manager.send_message(json.dumps(response), client_id, "read_storage")
            else:
                await self.manager.send_message(json.dumps({"status": "error", "message": message_dict['message']}), client_id, "read_storage")
        except Exception as e:
            logger.error(f"Error in read_storage: {str(e)}")
            await self.manager.send_message(json.dumps({"status": "error", "message": str(e)}), client_id, "read_storage")

    async def read_storage_indirect(self, message: dict, client_id: str, websocket: WebSocket):
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        
        try:
            status_code, message_dict = await read_storage(params['folder_id'])
            if status_code == 200:
                zip_filename = message_dict["path"]
                file_size = os.path.getsize(zip_filename)
                chunk_index = 0
                chunk_total = (file_size // CHUNK_SIZE) + 1

                with open(zip_filename, "rb") as file:
                    while chunk := file.read(CHUNK_SIZE):
                        encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                        response = {
                            'target_node': target_node_id,
                            'source_node': source_node_id,
                            'params': {
                                'status': "success",
                                'file_data': encoded_chunk,
                                'filename': os.path.basename(zip_filename),
                                'chunk_index': chunk_index,
                                'chunk_total': chunk_total
                            }
                        }
                        await self.manager.send_message(json.dumps(response), client_id, "read_storage_indirect")
                        chunk_index += 1

                # Send EOF
                response = {
                    'target_node': target_node_id,
                    'source_node': source_node_id,
                    'params': {
                        'status': "success",
                        'file_data': 'EOF',
                        'filename': os.path.basename(zip_filename),
                        'chunk_index': chunk_index,
                        'chunk_total': chunk_total
                    }
                }
                await self.manager.send_message(json.dumps(response), client_id, "read_storage_indirect")
            else:
                response = {
                    'target_node': target_node_id,
                    'source_node': source_node_id,
                    'params': {
                        'status': "error",
                        'message': message_dict['message']
                    }
                }
                await self.manager.send_message(json.dumps(response), client_id, "read_storage_indirect")
        except Exception as e:
            logger.error(f"Error in read_storage_indirect: {str(e)}")
            response = {
                'target_node': target_node_id,
                'source_node': source_node_id,
                'params': {
                    'status': "error",
                    'message': str(e)
                }
            }
            await self.manager.send_message(json.dumps(response), client_id, "read_storage_indirect")

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
            await self.manager.send_message(json.dumps({"status": "error", "message": str(e)}), client_id, "read_ipfs")

    async def read_ipfs_indirect_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "read_ipfs_indirect")
        try:
            while True:
                message = await websocket.receive_json()
                await self.read_ipfs_indirect(message, client_id, websocket)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "read_ipfs_indirect")
        except Exception as e:
            logger.error(f"Error in read_ipfs_indirect_endpoint: {str(e)}")
            await self.manager.send_message(json.dumps({"status": "error", "message": str(e)}), client_id, "read_ipfs_indirect")

    async def read_ipfs(self, params: dict, client_id: str, websocket: WebSocket):
        hash_or_name = params['hash_or_name']
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
                        encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                        response = {
                            "status": "success",
                            "data": {
                                'file_data': encoded_chunk,
                                'filename': f"{hash_or_name}.zip",
                                'chunk_index': chunk_index,
                                'chunk_total': chunk_total
                            }
                        }
                        await self.manager.send_message(json.dumps(response), client_id, "read_ipfs")
                else:
                    # For single file content
                    temp_filename = message_dict["path"]
                    file_size = os.path.getsize(temp_filename)
                    chunk_total = (file_size // CHUNK_SIZE) + 1
                    with open(temp_filename, "rb") as file:
                        for chunk_index in range(chunk_total):
                            chunk = file.read(CHUNK_SIZE)
                            encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                            response = {
                                "status": "success",
                                "data": {
                                    'file_data': encoded_chunk,
                                    'filename': message_dict["filename"],
                                    'chunk_index': chunk_index,
                                    'chunk_total': chunk_total
                                }
                            }
                            await self.manager.send_message(json.dumps(response), client_id, "read_ipfs")

                # Send EOF
                response = {
                    "status": "success",
                    "data": {
                        'file_data': 'EOF',
                        'filename': message_dict.get("filename", f"{hash_or_name}.zip"),
                        'chunk_index': chunk_total - 1,
                        'chunk_total': chunk_total
                    }
                }
                await self.manager.send_message(json.dumps(response), client_id, "read_ipfs")
            else:
                await self.manager.send_message(json.dumps({"status": "error", "message": message_dict['message']}), client_id, "read_ipfs")
        except Exception as e:
            logger.error(f"Error in read_ipfs: {str(e)}")
            await self.manager.send_message(json.dumps({"status": "error", "message": str(e)}), client_id, "read_ipfs")

    async def read_ipfs_indirect(self, message: dict, client_id: str, websocket: WebSocket):
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        
        try:
            status_code, message_dict = await read_from_ipfs_or_ipns(params['hash_or_name'])
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
                        encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                        response = {
                            'target_node': target_node_id,
                            'source_node': source_node_id,
                            'params': {
                                'status': "success",
                                'file_data': encoded_chunk,
                                'filename': f"{params['hash_or_name']}.zip",
                                'chunk_index': chunk_index,
                                'chunk_total': chunk_total
                            }
                        }
                        await self.manager.send_message(json.dumps(response), client_id, "read_ipfs_indirect")
                else:
                    # For single file content
                    temp_filename = message_dict["path"]
                    file_size = os.path.getsize(temp_filename)
                    chunk_total = (file_size // CHUNK_SIZE) + 1
                    with open(temp_filename, "rb") as file:
                        for chunk_index in range(chunk_total):
                            chunk = file.read(CHUNK_SIZE)
                            encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                            response = {
                                'target_node': target_node_id,
                                'source_node': source_node_id,
                                'params': {
                                    'status': "success",
                                    'file_data': encoded_chunk,
                                    'filename': message_dict["filename"],
                                    'chunk_index': chunk_index,
                                    'chunk_total': chunk_total
                                }
                            }
                            await self.manager.send_message(json.dumps(response), client_id, "read_ipfs_indirect")

                # Send EOF
                response = {
                    'target_node': target_node_id,
                    'source_node': source_node_id,
                    'params': {
                        'status': "success",
                        'file_data': 'EOF',
                        'filename': message_dict.get("filename", f"{params['hash_or_name']}.zip"),
                        'chunk_index': chunk_total - 1,
                        'chunk_total': chunk_total
                    }
                }
                await self.manager.send_message(json.dumps(response), client_id, "read_ipfs_indirect")
            else:
                response = {
                    'target_node': target_node_id,
                    'source_node': source_node_id,
                    'params': {
                        'status': "error",
                        'message': message_dict['message']
                    }
                }
                await self.manager.send_message(json.dumps(response), client_id, "read_ipfs_indirect")
        except Exception as e:
            logger.error(f"Error in read_ipfs_indirect: {str(e)}")
            response = {
                'target_node': target_node_id,
                'source_node': source_node_id,
                'params': {
                    'status': "error",
                    'message': str(e)
                }
            }
            await self.manager.send_message(json.dumps(response), client_id, "read_ipfs_indirect")

    async def launch_server(self):
        logger.info(f"Launching HTTP server...")
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="debug",
            timeout_keep_alive=300,
            limit_concurrency=200,
            backlog=4096,
            reload=True
        )
        server = uvicorn.Server(config)
        await server.serve()