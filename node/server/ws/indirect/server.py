import asyncio
import json
import websockets
import base64
import os
import io
from fastapi import UploadFile, WebSocket
from naptha_sdk.schemas import ModuleRun, ModuleRunInput
from node.utils import get_logger, get_config
from node.server.task import create_task, check_task
from node.server.user import register_user, check_user
from node.server.orchestration import create_task_run, update_task_run
from node.server.storage import write_to_ipfs, read_from_ipfs_or_ipns, write_storage, read_storage

logger = get_logger(__name__)
BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]
CHUNK_SIZE = 256 * 1024

class WebSocketIndirectServer:
    def __init__(self, uri: str):
        self.uri = uri
        self.temp_files = {}

    async def create_task_ws(self, websocket, message: dict) -> ModuleRun:
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            module_run_input = ModuleRunInput(**params)
            result = await create_task(module_run_input)
            response['params'] = result.model_dict()
            await websocket.send(json.dumps(response))
        except Exception as e:
            response['params'] = {'error': str(e)}
            await websocket.send(json.dumps(response))

    async def check_task_ws(self, websocket, message: dict) -> ModuleRun:
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        module_run = ModuleRun(**params)
        try:
            result = await check_task(module_run)
            response['params'] = result.model_dict()
            await websocket.send(json.dumps(response))
        except Exception as e:
            response['params'] = {'error': str(e)}
            await websocket.send(json.dumps(response))

    async def register_user_ws(self, websocket, message: dict) -> dict:
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
            await websocket.send(json.dumps(response))
        except Exception as e:
            logger.error(f"Error registering user: {e}")
            response['params'] = {'error': str(e)}
            await websocket.send(json.dumps(response))

    async def check_user_ws(self, websocket, message: dict) -> dict:
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
            await websocket.send(json.dumps(response))
        except Exception as e:
            response['params'] = {'error': str(e)}
            await websocket.send(json.dumps(response))

    async def create_task_run_ws(self, websocket, message: dict) -> ModuleRun:
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        try:
            module_run_input = ModuleRunInput(**params)
            module_run = await create_task_run(module_run_input)
            response['params'] = module_run.model_dict()
            await websocket.send(json.dumps(response))
        except Exception as e:
            response['params'] = {'error': str(e)}
            await websocket.send(json.dumps(response))

    async def update_task_run_ws(self, websocket, message: dict) -> ModuleRun:
        target_node_id = message['source_node']
        source_node_id = message['target_node']
        params = message['params']
        response = {
            'target_node': target_node_id,
            'source_node': source_node_id
        }
        module_run = ModuleRun(**params)
        try:
            module_run = await update_task_run(module_run)
            response['params'] = module_run.model_dict()
            await websocket.send(json.dumps(response))
        except Exception as e:
            response['params'] = {'error': str(e)}
            await websocket.send(json.dumps(response))

    async def write_storage_ws(self, websocket: WebSocket, message: dict):
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
                chunk = base64.b64decode(file_data)
                if temp_filepath not in self.temp_files:
                    self.temp_files[temp_filepath] = temp_filepath
                with open(self.temp_files[temp_filepath], "ab") as temp_file:
                    temp_file.write(chunk)
                logger.info(f"Received chunk for file {filename}")
                response['params'] = {'status': 'Chunk received'}
            
            logger.info(f"Response: {response}")
            await websocket.send(json.dumps(response))
        except Exception as e:
            response['params'] = {'error': str(e)}
            await websocket.send(json.dumps(response))

    async def write_to_ipfs_ws(self, websocket: WebSocket, message: dict):
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
                chunk = base64.b64decode(file_data)
                if temp_filepath not in self.temp_files:
                    self.temp_files[temp_filepath] = temp_filepath
                with open(self.temp_files[temp_filepath], "ab") as temp_file:
                    temp_file.write(chunk)
                logger.info(f"Received chunk for file {filename}")
                response['params'] = {'status': 'Chunk received'}
            
            logger.info(f"Response: {response}")
            await websocket.send(json.dumps(response))
        except Exception as e:
            response['params'] = {'error': str(e)}
            await websocket.send(json.dumps(response))

    async def read_storage_ws(self, websocket: WebSocket, message: dict):
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
                        await websocket.send(json.dumps(response))
                        chunk_index += 1

                response['params'] = {
                    'file_data': 'EOF',
                    'filename': os.path.basename(zip_filename),
                    'chunk_index': chunk_index,
                    'chunk_total': (file_size // CHUNK_SIZE) + 1
                }
                await websocket.send(json.dumps(response))
                logger.info(f"Final EOF chunk sent")
            else:
                response['params'] = {'error': message_dict['message']}
                await websocket.send(json.dumps(response))
        except Exception as e:
            response['params'] = {'error': str(e)}
            await websocket.send(json.dumps(response))

    async def read_from_ipfs_or_ipns_ws(self, websocket: WebSocket, message: dict):
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
                        await websocket.send(json.dumps(response))
                        logger.info(f"Sent chunk {chunk_index} of {hash_or_name}.zip")
                        chunk_index += 1
                else:
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
                            await websocket.send(json.dumps(response))
                            logger.info(f"Sent chunk {chunk_index} of {message_dict['filename']}")
                            chunk_index += 1
                
                response['params'] = {
                    'file_data': 'EOF',
                    'filename': message_dict.get("filename", f"{hash_or_name}.zip"),
                    'chunk_index': chunk_index,
                    'chunk_total': (file_size // CHUNK_SIZE) + 1
                }
                await websocket.send(json.dumps(response))
                logger.info(f"Final EOF chunk sent")
            else:
                response['params'] = {'error': message_dict['message']}
                await websocket.send(json.dumps(response))
        except Exception as e:
            response['params'] = {'error': str(e)}
            await websocket.send(json.dumps(response))

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
                            await self.create_task_ws(websocket, message)
                        elif message["path"] == "check_task":
                            await self.check_task_ws(websocket, message)
                        elif message["path"] == "check_user":
                            await self.check_user_ws(websocket, message)
                        elif message["path"] == "register_user":
                            await self.register_user_ws(websocket, message)
                        elif message["path"] == "create_task_run":
                            await self.create_task_run_ws(websocket, message)
                        elif message["path"] == "update_task_run":
                            await self.update_task_run_ws(websocket, message)
                        elif message["path"] == "write_to_ipfs":
                            await self.write_to_ipfs_ws(websocket, message)
                        elif message["path"] == "read_from_ipfs":
                            await self.read_from_ipfs_or_ipns_ws(websocket, message)
                        elif message["path"] == "write_storage":
                            await self.write_storage_ws(websocket, message)
                        elif message["path"] == "read_storage":
                            await self.read_storage_ws(websocket, message)
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