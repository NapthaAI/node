import uuid
import websockets
import json
from datetime import datetime
from typing import Dict, Optional
from naptha_sdk.schemas import ModuleRun, ModuleRunInput
from naptha_sdk.utils import get_logger

logger = get_logger(__name__)

def parse_datetime(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                try:
                    data[key] = datetime.fromisoformat(value)
                except ValueError:
                    pass
            elif isinstance(value, (dict, list)):
                parse_datetime(value)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, (dict, list)):
                parse_datetime(item)
    return data

class Node:
    def __init__(self, node_url: str):
        self.node_url = node_url
        if 'ws' not in self.node_url:
            logger.info(f"Adding ws to ws_url: {self.node_url}")
            self.node_url = f'ws://{self.node_url}'
        self.ws = None

    async def connect(self, action: str):
        client_id = str(uuid.uuid4())
        full_url = f"{self.node_url}/ws/{client_id}/{action}"
        logger.info(f"Connecting to WebSocket: {full_url}")
        self.ws = await websockets.connect(full_url)

    async def disconnect(self):
        if self.ws:
            await self.ws.close()
            self.ws = None

    async def send_receive(self, data, action: str):
        await self.connect(action)
        
        try:
            message = json.dumps(data)
            logger.info(f"Sending message: {message}")
            await self.ws.send(message)
            
            response = await self.ws.recv()
            logger.info(f"Received response: {response}")
            return json.loads(response)
        finally:
            await self.disconnect()

    async def create_task(self, module_run_input: ModuleRunInput) -> ModuleRun:
        data = {
            "module_name": module_run_input.module_name,
            "consumer_id": module_run_input.consumer_id,
            "module_params": module_run_input.module_params,
            "module_type": module_run_input.module_type
        }
        response = await self.send_receive(data, "create_task")
        
        if response['status'] == 'success':
            logger.info(f"Task created successfully: {response['data']}")
            response['data'] = parse_datetime(response['data'])
            return ModuleRun(**response['data'])
        else:
            logger.error(f"Error creating task: {response['message']}")
            raise Exception(response['message'])

    async def run_task(self, module_run_input: ModuleRunInput) -> ModuleRun:
        return await self.create_task(module_run_input)

    async def check_user(self, user_input: Dict[str, str]):
        response = await self.send_receive(user_input, "check_user")
        logger.info(f"Check user response: {response}")
        return response

    async def register_user(self, user_input: Dict[str, str]):
        response = await self.send_receive(user_input, "register_user")
        logger.info(f"Register user response: {response}")
        return response