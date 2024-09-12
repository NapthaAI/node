import json
import base64
from pydantic import BaseModel
from fastapi import UploadFile
from node.utils import get_logger, get_config
from node.server.storage import write_to_ipfs, read_from_ipfs_or_ipns, write_storage, read_storage
from fastapi import WebSocket
import io
import os


logger = get_logger(__name__)
BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]

CHUNK_SIZE = 256 * 1024 

class FileData(BaseModel):
    filename: str
    file: str  # base64 encoded

def decode_file_data(file_data: str, filename: str) -> UploadFile:
    """Decode a base64 encoded file to an UploadFile object."""
    file_bytes = base64.b64decode(file_data)
    file_stream = io.BytesIO(file_bytes)
    return UploadFile(filename=filename, file=file_stream)

def encode_file_data(file_path: str) -> str:
    """Encode a file to a base64 encoded string."""
    with open(file_path, "rb") as file:
        file_data = file.read()
    return base64.b64encode(file_data).decode('utf-8')

temp_files = {}

async def write_storage_ws(websocket: WebSocket, message: dict):
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
            if temp_filepath in temp_files:
                with open(temp_files[temp_filepath], "rb") as temp_file:
                    file = UploadFile(filename=filename, file=temp_file)
                    status_code, message_dict = await write_storage(file)
                    logger.info(f"Statau code: {status_code}, massage: {message_dict}")
                    if status_code == 201:
                        response['params'] = message_dict
                    else:
                        response['params'] = {'error': message_dict['message']}
                os.remove(temp_files[temp_filepath])
                del temp_files[temp_filepath]
                logger.info(f"Completed file transfer and saved file: {filename}")
            else:
                response['params'] = {'error': 'File transfer not found'}
        else:
            # Accumulate chunks
            chunk = base64.b64decode(file_data)
            if temp_filepath not in temp_files:
                temp_files[temp_filepath] = temp_filepath
            with open(temp_files[temp_filepath], "ab") as temp_file:
                temp_file.write(chunk)
            logger.info(f"Received chunk for file {filename}")
            response['params'] = {'status': 'Chunk received'}
        
        logger.info(f"Response: {response}")
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))

async def write_to_ipfs_ws(websocket: WebSocket, message: dict):
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
            if temp_filepath in temp_files:
                with open(temp_files[temp_filepath], "rb") as temp_file:
                    file = UploadFile(filename=filename, file=temp_file)
                    status_code, message_dict = await write_to_ipfs(file, publish_to_ipns, update_ipns_name)
                    logger.info(f"Status code: {status_code}, message: {message_dict}")
                    if status_code == 201:
                        response['params'] = message_dict
                    else:
                        response['params'] = {'error': message_dict['message']}
                os.remove(temp_files[temp_filepath])
                del temp_files[temp_filepath]
                logger.info(f"Completed file transfer and saved file: {filename}")
            else:
                response['params'] = {'error': 'File transfer not found'}
        else:
            # Accumulate chunks
            chunk = base64.b64decode(file_data)
            if temp_filepath not in temp_files:
                temp_files[temp_filepath] = temp_filepath
            with open(temp_files[temp_filepath], "ab") as temp_file:
                temp_file.write(chunk)
            logger.info(f"Received chunk for file {filename}")
            response['params'] = {'status': 'Chunk received'}
        
        logger.info(f"Response: {response}")
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))


async def read_storage_ws(websocket: WebSocket, message: dict):
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

async def read_from_ipfs_or_ipns_ws(websocket: WebSocket, message: dict):
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
                    await websocket.send(json.dumps(response))
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


