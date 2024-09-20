import asyncio
import json
import base64
import os
import io
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
from naptha_sdk.schemas import ModuleRun, ModuleRunInput
from node.utils import get_logger, get_config
from node.user import register_user, check_user
from node.server.orchestration import create_task_run, update_task_run
from node.storage.storage import write_to_ipfs, read_from_ipfs_or_ipns, write_storage, read_storage
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError


logger = get_logger(__name__)
BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]
CHUNK_SIZE = 256 * 1024

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

class WebSocketIndirectServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
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

        self.app.add_api_websocket_route("/ws/create_task/{client_id}", self.create_task_endpoint)
        self.app.add_api_websocket_route("/ws/check_task/{client_id}", self.check_task_endpoint)
        self.app.add_api_websocket_route("/ws/register_user/{client_id}", self.register_user_endpoint)
        self.app.add_api_websocket_route("/ws/check_user/{client_id}", self.check_user_endpoint)
        self.app.add_api_websocket_route("/ws/create_task_run/{client_id}", self.create_task_run_endpoint)
        self.app.add_api_websocket_route("/ws/update_task_run/{client_id}", self.update_task_run_endpoint)
        self.app.add_api_websocket_route("/ws/write_storage/{client_id}", self.write_storage_endpoint)
        self.app.add_api_websocket_route("/ws/write_to_ipfs/{client_id}", self.write_to_ipfs_endpoint)
        self.app.add_api_websocket_route("/ws/read_storage/{client_id}", self.read_storage_endpoint)
        self.app.add_api_websocket_route("/ws/read_from_ipfs/{client_id}", self.read_from_ipfs_endpoint)

    async def create_task_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "create_task")
        try:
            while True:
                message = await websocket.receive_json()
                await self.create_task_ws(websocket, message, client_id)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "create_task")

    async def check_task_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "check_task")
        try:
            while True:
                message = await websocket.receive_json()
                await self.check_task_ws(websocket, message, client_id)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "check_task")

    async def register_user_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "register_user")
        try:
            while True:
                message = await websocket.receive_json()
                await self.register_user_ws(websocket, message, client_id)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "register_user")

    async def check_user_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "check_user")
        try:
            while True:
                message = await websocket.receive_json()
                await self.check_user_ws(websocket, message, client_id)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "check_user")

    async def create_task_run_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "create_task_run")
        try:
            while True:
                message = await websocket.receive_json()
                await self.create_task_run_ws(websocket, message, client_id)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "create_task_run")

    async def update_task_run_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "update_task_run")
        try:
            while True:
                message = await websocket.receive_json()
                await self.update_task_run_ws(websocket, message, client_id)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "update_task_run")

    async def write_storage_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "write_storage")
        try:
            while True:
                message = await websocket.receive_json()
                await self.write_storage_ws(websocket, message, client_id)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "write_storage")

    async def write_to_ipfs_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "write_to_ipfs")
        try:
            while True:
                message = await websocket.receive_json()
                await self.write_to_ipfs_ws(websocket, message, client_id)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "write_to_ipfs")

    async def read_storage_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "read_storage")
        try:
            while True:
                message = await websocket.receive_json()
                await self.read_storage_ws(websocket, message, client_id)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "read_storage")

    async def read_from_ipfs_endpoint(self, websocket: WebSocket, client_id: str):
        await self.manager.connect(websocket, client_id, "read_from_ipfs")
        try:
            while True:
                message = await websocket.receive_json()
                await self.read_from_ipfs_or_ipns_ws(websocket, message, client_id)
        except WebSocketDisconnect:
            self.manager.disconnect(client_id, "read_from_ipfs")

    async def create_task(self, module_run_input: ModuleRunInput) -> ModuleRun:
        """
        Create a task and return the task
        """
        # Implement the create_task logic here
        # This is a placeholder implementation
        return ModuleRun(**module_run_input.dict())

    async def check_task(self, module_run: ModuleRun) -> ModuleRun:
        """
        Check a task and return the task
        """
        # Implement the check_task logic here
        # This is a placeholder implementation
        return module_run

    async def create_task_ws(self, websocket, message: dict, client_id: str) -> ModuleRun:
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
            result = await self.create_task(module_run_input)
            response['params'] = result.model_dict()
            await self.manager.send_message(json.dumps(response), client_id, "create_task")
        except Exception as e:
            response['params'] = {'error': str(e)}
            await self.manager.send_message(json.dumps(response), client_id, "create_task")

    async def check_task_ws(self, websocket, message: dict, client_id: str) -> ModuleRun:
        """
        Check a task and return the task
        """
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        module_run = ModuleRun(**params)
        try:
            result = await self.check_task(module_run)
            response['params'] = result.model_dict()
            await self.manager.send_message(json.dumps(response), client_id, "check_task")
        except Exception as e:
            response['params'] = {'error': str(e)}
            await self.manager.send_message(json.dumps(response), client_id, "check_task")

    async def register_user_ws(self, websocket, message: Dict, client_id: str) -> Dict:
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

    async def check_user_ws(self, websocket, message: Dict, client_id: str) -> Dict:
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

    async def create_task_run_ws(self, websocket, message: dict, client_id: str) -> ModuleRun:
        """
        Create a task run via a websocket connection.
        """
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            module_run_input = ModuleRunInput(
                **params
            )
            module_run = await create_task_run(module_run_input)
            response['params'] = module_run.model_dict()
            await self.manager.send_message(json.dumps(response), client_id, "create_task_run")
        except Exception as e:
            response['params'] = {'error': str(e)}
            await self.manager.send_message(json.dumps(response), client_id, "create_task_run")

    async def update_task_run_ws(self, websocket, message: dict, client_id: str) -> ModuleRun:
        """
        Update a task run via a websocket connection.
        """
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        module_run = ModuleRun(**params)
        try:
            module_run = ModuleRun(**params)
            module_run = await update_task_run(module_run)
            response['params'] = module_run.model_dict()
            await self.manager.send_message(json.dumps(response), client_id, "update_task_run")
        except Exception as e:
            response['params'] = {'error': str(e)}
            await self.manager.send_message(json.dumps(response), client_id, "update_task_run")


    async def write_storage_ws(self, websocket: WebSocket, message: dict, client_id: str):
        """Write files to the storage."""
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        filename = params['filename']
        file_data = params['file_data']
        
        temp_dir = os.path.join(BASE_OUTPUT_DIR, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_filepath = os.path.join(temp_dir, f"{source_node_id}_{filename}.part")

        try:
            if file_data == 'EOF':
                # Handle EOF: process the accumulated file
                if temp_filepath in self.temp_files:
                    with open(self.temp_files[temp_filepath], "rb") as temp_file:
                        file = UploadFile(filename=filename, file=temp_file)
                        status_code, message_dict = await write_storage(file)
                        logger.info(f"Status code: {status_code}, message: {message_dict}")
                        if status_code == 201:
                            response['params'] = message_dict
                        else:
                            response['params'] = {'error': message_dict['message']}
                    os.remove(self.temp_files[temp_filepath])
                    del self.temp_files[temp_filepath]
                    logger.info(f"Completed file transfer and saved file: {filename}")
                else:
                    response['params'] = {'error': 'File transfer not found'}
            else:
                # Accumulate chunks
                chunk = base64.b64decode(file_data)
                if temp_filepath not in self.temp_files:
                    self.temp_files[temp_filepath] = temp_filepath
                with open(self.temp_files[temp_filepath], "ab") as temp_file:
                    temp_file.write(chunk)
                logger.info(f"Received chunk for file {filename}")
                response['params'] = {'status': 'Chunk received'}
            
            logger.info(f"Response: {response}")
            await self.manager.send_message(json.dumps(response), client_id, "write_storage")
        except Exception as e:
            response['params'] = {'error': str(e)}
            await self.manager.send_message(json.dumps(response), client_id, "write_storage")

    async def write_to_ipfs_ws(self, websocket: WebSocket, message: dict, client_id: str):
        """Write a file to IPFS, optionally publish to IPNS or update an existing IPNS record."""
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        filename = params['filename']
        file_data = params['file_data']
        publish_to_ipns = params.get('publish_to_ipns', False)
        update_ipns_name = params.get('update_ipns_name')
        
        temp_dir = os.path.join(BASE_OUTPUT_DIR, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        temp_filepath = os.path.join(temp_dir, f"{source_node_id}_{filename}.part")

        try:
            if file_data == 'EOF':
                # Handle EOF: process the accumulated file
                if temp_filepath in self.temp_files:
                    with open(self.temp_files[temp_filepath], "rb") as temp_file:
                        file = UploadFile(filename=filename, file=temp_file)
                        status_code, message_dict = await write_to_ipfs(file, publish_to_ipns, update_ipns_name)
                        logger.info(f"Status code: {status_code}, message: {message_dict}")
                        if status_code == 201:
                            response['params'] = message_dict
                        else:
                            response['params'] = {'error': message_dict['message']}
                    os.remove(self.temp_files[temp_filepath])
                    del self.temp_files[temp_filepath]
                    logger.info(f"Completed file transfer and saved file: {filename}")
                else:
                    response['params'] = {'error': 'File transfer not found'}
            else:
                # Accumulate chunks
                chunk = base64.b64decode(file_data)
                if temp_filepath not in self.temp_files:
                    self.temp_files[temp_filepath] = temp_filepath
                with open(self.temp_files[temp_filepath], "ab") as temp_file:
                    temp_file.write(chunk)
                logger.info(f"Received chunk for file {filename}")
                response['params'] = {'status': 'Chunk received'}
            
            logger.info(f"Response: {response}")
            await self.manager.send_message(json.dumps(response), client_id, "write_to_ipfs")
        except Exception as e:
            response['params'] = {'error': str(e)}
            await self.manager.send_message(json.dumps(response), client_id, "write_to_ipfs")

    async def read_storage_ws(self, websocket: WebSocket, message: dict, client_id: str):
        """Get the output directory for a job_id and serve it as a zip file."""
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        logger.info(f"Read storage response: {response}")
        try:
            job_id = params['folder_id']
            status_code, message_dict = await read_storage(job_id)
            if status_code == 200:
                zip_filename = message_dict["path"]
                file_size = os.path.getsize(zip_filename)
                chunk_index = 0
                with open(zip_filename, "rb") as file:
                    while chunk := file.read(CHUNK_SIZE):
                        encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                        response['params'] = {
                            'file_data': encoded_chunk,
                            'filename': os.path.basename(zip_filename),
                            'chunk_index': chunk_index,
                            'chunk_total': (file_size // CHUNK_SIZE) + 1
                        }
                        await self.manager.send_message(json.dumps(response), client_id, "read_storage")
                        chunk_index += 1

                response['params'] = {
                    'file_data': 'EOF',
                    'filename': os.path.basename(zip_filename),
                    'chunk_index': chunk_index,
                    'chunk_total': (file_size // CHUNK_SIZE) + 1
                }
                await self.manager.send_message(json.dumps(response), client_id, "read_storage")
                logger.info(f"Final EOF chunk sent")
            else:
                response['params'] = {'error': message_dict['message']}
                await self.manager.send_message(json.dumps(response), client_id, "read_storage")
        except Exception as e:
            response['params'] = {'error': str(e)}
            await self.manager.send_message(json.dumps(response), client_id, "read_storage")

    async def read_from_ipfs_or_ipns_ws(self, websocket: WebSocket, message: dict, client_id: str):
        """Read a file from IPFS or IPNS."""
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            hash_or_name = params['hash_or_name']
            status_code, message_dict = await read_from_ipfs_or_ipns(hash_or_name)
            if status_code == 200:
                if "content" in message_dict:
                    # For zipped directory content
                    content = message_dict["content"]
                    file_size = len(content)
                    chunk_index = 0
                    for i in range(0, file_size, CHUNK_SIZE):
                        chunk = content[i:i+CHUNK_SIZE]
                        encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                        response['params'] = {
                            'file_data': encoded_chunk,
                            'filename': f"{hash_or_name}.zip",
                            'chunk_index': chunk_index,
                            'chunk_total': (file_size // CHUNK_SIZE) + 1
                        }
                        await self.manager.send_message(json.dumps(response), client_id, "read_from_ipfs")
                        logger.info(f"Sent chunk {chunk_index} of {hash_or_name}.zip")
                        chunk_index += 1
                else:
                    # For single file content
                    temp_filename = message_dict["path"]
                    file_size = os.path.getsize(temp_filename)
                    chunk_index = 0
                    with open(temp_filename, "rb") as file:
                        while chunk := file.read(CHUNK_SIZE):
                            encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                            response['params'] = {
                                'file_data': encoded_chunk,
                                'filename': message_dict["filename"],
                                'chunk_index': chunk_index,
                                'chunk_total': (file_size // CHUNK_SIZE) + 1
                            }
                            await self.manager.send_message(json.dumps(response), client_id, "read_from_ipfs")
                            logger.info(f"Sent chunk {chunk_index} of {message_dict['filename']}")
                            chunk_index += 1
                
                response['params'] = {
                    'file_data': 'EOF',
                    'filename': message_dict.get("filename", f"{hash_or_name}.zip"),
                    'chunk_index': chunk_index,
                    'chunk_total': (file_size // CHUNK_SIZE) + 1
                }
                await self.manager.send_message(json.dumps(response), client_id, "read_from_ipfs")
                logger.info(f"Final EOF chunk sent")
            else:
                response['params'] = {'error': message_dict['message']}
                await self.manager.send_message(json.dumps(response), client_id, "read_from_ipfs")
        except Exception as e:
            response['params'] = {'error': str(e)}
            await self.manager.send_message(json.dumps(response), client_id, "read_from_ipfs")

    def launch_server(self):
        import uvicorn
        logger.info(f"Launching WebSocket server on {self.host}:{self.port}")
        uvicorn.run(self.app, host=self.host, port=self.port)