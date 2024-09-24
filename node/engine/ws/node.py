import uuid
import websockets
import json
from datetime import datetime
from typing import Dict, Optional
from node.schemas import AgentRun, AgentRunInput
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
        self.connections = {}

    async def connect(self, action: str):
        client_id = str(uuid.uuid4())
        full_url = f"{self.node_url}/ws/{action}/{client_id}"
        logger.info(f"Connecting to WebSocket: {full_url}")
        ws = await websockets.connect(full_url)
        self.connections[client_id] = ws
        self.current_client_id = client_id
        return client_id

    async def disconnect(self, client_id: str):
        if client_id in self.connections:
            await self.connections[client_id].close()
            del self.connections[client_id]
        if self.current_client_id == client_id:
            self.current_client_id = None

    async def send_receive(self, data, action: str):
        client_id = await self.connect(action)
        
        try:
            message = json.dumps(data)
            logger.info(f"Sending message: {message}")
            await self.connections[client_id].send(message)
            
            response = await self.connections[client_id].recv()
            logger.info(f"Received response: {response}")
            return json.loads(response)
        finally:
            await self.disconnect(client_id)

    async def run_agent(self, agent_run_input: AgentRunInput) -> AgentRun:
        data = {
            "agent_name": agent_run_input.agent_name,
            "consumer_id": agent_run_input.consumer_id,
            "agent_run_params": agent_run_input.agent_run_params,
            "agent_run_type": agent_run_input.agent_run_type
        }
        response = await self.send_receive(data, "run_agent")
        
        if response['status'] == 'success':
            logger.info(f"Ran agent successfully: {response['data']}")
            response['data'] = parse_datetime(response['data'])
            return AgentRun(**response['data'])
        else:
            logger.error(f"Error running agent: {response['message']}")
            raise Exception(response['message'])

    async def check_user(self, user_input: Dict[str, str]):
        response = await self.send_receive(user_input, "check_user")
        logger.info(f"Check user response: {response}")
        return response

    async def register_user(self, user_input: Dict[str, str]):
        response = await self.send_receive(user_input, "register_user")
        logger.info(f"Register user response: {response}")
        return response

    async def send_receive_multiple(self, data_list, action: str):
        results = []

        for data in data_list:
            client_id = await self.connect(action)

            message = json.dumps(data)
            logger.info(f"Sending message: {message}")
            await self.connections[client_id].send(message)

            response = await self.connections[client_id].recv()
            logger.info(f"Received response: {response}")
            results.append(json.loads(response))

            await self.disconnect(client_id)

        return results

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for client_id in list(self.connections.keys()):
            await self.disconnect(client_id)