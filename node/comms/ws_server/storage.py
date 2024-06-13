import json
import base64
from pydantic import BaseModel
from fastapi import UploadFile
from node.utils import get_logger, get_config
from node.comms.storage import write_to_ipfs, read_from_ipfs, write_storage, read_storage
from fastapi import WebSocket
import io

logger = get_logger(__name__)
BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]

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

async def write_storage_ws(websocket: WebSocket, message: dict):
    """Write files to the storage."""
    target_node_id = message['source_node']
    source_node_id = message['target_node']
    params = message['params']
    response = {
        'target_node': target_node_id,
        'source_node': source_node_id
    }
    try:
        file_data = params['file_data']
        filename = params['filename']
        file = decode_file_data(file_data, filename)
        status_code, message_dict = await write_storage(file)
        if status_code == 201:
            response['params'] = message_dict
        else:
            response['params'] = {'error': message_dict['message']}
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))

async def read_storage_ws(websocket: WebSocket, message: dict):
    """Get the output directory for a job_id and serve it as a tar.gz file."""
    target_node_id = message['source_node']
    source_node_id = message['target_node']
    params = message['params']
    response = {
        'target_node': target_node_id,
        'source_node': source_node_id
    }
    try:
        job_id = params['folder_id']
        status_code, message_dict = await read_storage(job_id)
        if status_code == 200:
            temp_filename = message_dict["path"]
            file_data = encode_file_data(temp_filename)
            response['params'] = {
                'file_data': file_data,
                'filename': message_dict["filename"]
            }
        else:
            response['params'] = {'error': message_dict['message']}
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))

async def write_to_ipfs_ws(websocket: WebSocket, message: dict):
    """Write a file to IPFS and pin it."""
    target_node_id = message['source_node']
    source_node_id = message['target_node']
    params = message['params']
    response = {
        'target_node': target_node_id,
        'source_node': source_node_id
    }
    try:
        file_data = params['file_data']
        filename = params['filename']
        file = decode_file_data(file_data, filename)
        status_code, message_dict = await write_to_ipfs(file)
        if status_code == 201:
            response['params'] = message_dict
        else:
            response['params'] = {'error': message_dict['message']}
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))

async def read_from_ipfs_ws(websocket: WebSocket, message: dict):
    """Read a file from IPFS."""
    target_node_id = message['source_node']
    source_node_id = message['target_node']
    params = message['params']
    response = {
        'target_node': target_node_id,
        'source_node': source_node_id
    }
    try:
        ipfs_hash = params['ipfs_hash']
        status_code, message_dict = await read_from_ipfs(ipfs_hash)
        if status_code == 200:
            temp_filename = message_dict["path"]
            file_data = encode_file_data(temp_filename)
            response['params'] = {
                'file_data': file_data,
                'filename': message_dict["filename"]
            }
        else:
            response['params'] = {'error': message_dict['message']}
        await websocket.send(json.dumps(response))
    except Exception as e:
        response['params'] = {'error': str(e)}
        await websocket.send(json.dumps(response))
