import asyncio
from datetime import datetime
import httpx
from httpx import HTTPStatusError, RemoteProtocolError
import json
from node.utils import get_logger
from node.schemas import AgentRun, AgentRunInput
import time
import traceback
from typing import Dict, Any
import uuid
import websockets

logger = get_logger(__name__)
HTTP_TIMEOUT = 300

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
    def __init__(self, node_url, server_type):
        self.node_url = node_url
        self.server_type = server_type
        self.connections = {}
        self.access_token = None

    async def connect_ws(self, action: str):
        client_id = str(uuid.uuid4())
        full_url = f"{self.node_url}/ws/{action}/{client_id}"
        logger.info(f"Connecting to WebSocket: {full_url}")
        ws = await websockets.connect(full_url)
        self.connections[client_id] = ws
        self.current_client_id = client_id
        return client_id

    async def disconnect_ws(self, client_id: str):
        if client_id in self.connections:
            await self.connections[client_id].close()
            del self.connections[client_id]
        if self.current_client_id == client_id:
            self.current_client_id = None

    async def send_receive_ws(self, data, action: str):
        client_id = await self.connect_ws(action)
        
        try:
            message = json.dumps(data)
            logger.info(f"Sending message: {message}")
            await self.connections[client_id].send(message)
            
            response = await self.connections[client_id].recv()
            logger.info(f"Received response: {response}")
            return json.loads(response)
        finally:
            await self.disconnect_ws(client_id)

    async def check_user(self, user_input):
        print("Checking user... ", user_input)
        if self.server_type == 'http':
            return await self.check_user_http(user_input)
        elif self.server_type == 'ws':
            return await self.check_user_ws(user_input)
        else:
            raise ValueError("Invalid server type")

    async def register_user(self, user_input):
        if self.server_type == 'http':
            result = await self.register_user_http(user_input)
        elif self.server_type == 'ws':
            result = await self.register_user_ws(user_input)
        else:
            raise ValueError("Invalid server type")
        
        if result is None:
            raise ValueError("User registration failed: returned None")
        
        return result

    async def run_agent(self, agent_run_input: AgentRunInput) -> AgentRun:
        if self.server_type == 'http':
            result = await self.run_agent_and_poll(agent_run_input)
        elif self.server_type == 'ws':
            result = await self.run_agent_ws(agent_run_input)
        else:
            raise ValueError("Invalid server type")
        
        if result is None:
            raise ValueError("run_agent returned None")
        
        return result

    async def run_agent_http(self, agent_run_input: AgentRunInput) -> Dict[str, Any]:
        """
        Run a agent on a node
        """
        print("Running agent...")
        print(f"Node URL: {self.node_url}")

        endpoint = self.node_url + "/agent/run"
        
        if isinstance(agent_run_input, dict):
            agent_run_input = AgentRunInput(**agent_run_input)

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                headers = {
                    'Content-Type': 'application/json', 
                    'Authorization': f'Bearer {self.access_token}',  
                }
                response = await client.post(
                    endpoint, 
                    json=agent_run_input.model_dict(),
                    headers=headers
                )
                response.raise_for_status()
            return AgentRun(**json.loads(response.text))
        except HTTPStatusError as e:
            logger.info(f"HTTP error occurred: {e}")
            raise  
        except RemoteProtocolError as e:
            error_msg = f"Run agent failed to connect to the server at {self.node_url}. Please check if the server URL is correct and the server is running. Error details: {str(e)}"
            logger.error(error_msg)
            raise 
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            raise

    async def run_agent_ws(self, agent_run_input: AgentRunInput) -> AgentRun:
        data = {
            "agent_name": agent_run_input.agent_name,
            "consumer_id": agent_run_input.consumer_id,
            "agent_run_params": agent_run_input.agent_run_params,
            "agent_run_type": agent_run_input.agent_run_type
        }
        response = await self.send_receive_ws(data, "run_agent")
        
        if response['status'] == 'success':
            logger.info(f"Ran agent successfully: {response['data']}")
            response['data'] = parse_datetime(response['data'])
            return AgentRun(**response['data'])
        else:
            logger.error(f"Error running agent: {response['message']}")
            raise Exception(response['message'])

    async def run_agent_and_poll(self, agent_run_input: AgentRunInput) -> AgentRun:
        assert self.server_type == 'http', "run_agent_and_poll should only be called for HTTP server type"
        agent_run = await self.run_agent_http(agent_run_input)
        print(f"Agent run started: {agent_run}")

        current_results_len = 0
        while True:
            agent_run = await self.check_agent_run_http(agent_run)
            output = f"{agent_run.status} {agent_run.agent_run_type} {agent_run.agent_name}"
            if len(agent_run.child_runs) > 0:
                output += f", agent {len(agent_run.child_runs)} {agent_run.child_runs[-1].agent_name} (node: {agent_run.child_runs[-1].worker_nodes[0]})"
            print(output)

            if len(agent_run.results) > current_results_len:
                print("Output: ", agent_run.results[-1])
                current_results_len += 1

            if agent_run.status == 'completed':
                break
            if agent_run.status == 'error':
                break

            time.sleep(3)

        if agent_run.status == 'completed':
            print(agent_run.results)
        else:
            print(agent_run.error_message)
        return agent_run

    async def check_user_http(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if a user exists on a node
        """
        endpoint = self.node_url + "/user/check"
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                headers = {
                    'Content-Type': 'application/json', 
                }
                response = await client.post(
                    endpoint, 
                    json=user_input,
                    headers=headers
                )
                response.raise_for_status()
            return json.loads(response.text)
        except HTTPStatusError as e:
            logger.info(f"HTTP error occurred: {e}")
            raise  
        except RemoteProtocolError as e:
            error_msg = f"Check user failed to connect to the server at {self.node_url}. Please check if the server URL is correct and the server is running. Error details: {str(e)}"
            logger.info(error_msg)
            raise 
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}")
            raise

    async def check_user_ws(self, user_input: Dict[str, str]):
        response = await self.send_receive_ws(user_input, "check_user")
        logger.info(f"Check user response: {response}")
        return response

    async def register_user_http(self, user_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Register a user on a node
        """
        endpoint = self.node_url + "/user/register"
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                headers = {
                    'Content-Type': 'application/json', 
                }
                response = await client.post(
                    endpoint, 
                    json=user_input,
                    headers=headers
                )
                response.raise_for_status()
            return json.loads(response.text)
        except HTTPStatusError as e:
            logger.info(f"HTTP error occurred: {e}")
            raise  
        except RemoteProtocolError as e:
            error_msg = f"Register user failed to connect to the server at {self.node_url}. Please check if the server URL is correct and the server is running. Error details: {str(e)}"
            logger.error(error_msg)
            raise 
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}")
            raise

    async def register_user_ws(self, user_input: Dict[str, str]):
        response = await self.send_receive_ws(user_input, "register_user")
        logger.info(f"Register user response: {response}")
        return response

    async def check_agent_run_http(self, agent_run: AgentRun) -> AgentRun:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{self.node_url}/agent/check", json=agent_run.model_dict()
                )
                response.raise_for_status()
            return AgentRun(**json.loads(response.text))
        except HTTPStatusError as e:
            logger.info(f"HTTP error occurred: {e}")
            raise  
        except Exception as e:
            logger.info(f"An unexpected error occurred: {e}")
            logger.info(f"Full traceback: {traceback.format_exc()}")

    async def send_receive_multiple(self, data_list, action: str):
        results = []

        for data in data_list:
            client_id = await self.connect_ws(action)

            message = json.dumps(data)
            logger.info(f"Sending message: {message}")
            await self.connections[client_id].send(message)

            response = await self.connections[client_id].recv()
            logger.info(f"Received response: {response}")
            results.append(json.loads(response))

            await self.disconnect_ws(client_id)

        return results

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for client_id in list(self.connections.keys()):
            await self.disconnect_ws(client_id)


class NodeIndirect:
    def __init__(self, node_url: str, routing_url: str):
        self.node_url = node_url
        self.routing_url = routing_url
        if 'ws' not in self.routing_url:
            self.routing_url = f'ws://{self.routing_url}'
        self.lock = asyncio.Lock()
        self.websocket = None

    async def get_websocket(self):
        async with self.lock:
            if self.websocket is None or self.websocket.closed:
                full_url = f"{self.routing_url}/ws"
                logger.info(f"Connecting to WebSocket: {full_url}")
                self.websocket = await websockets.connect(full_url)
            return self.websocket

    async def send_receive(self, data: Dict, action: str):
        websocket = await self.get_websocket()
        source_node = f"{self.node_url}"

        message = {
            "target_node": self.node_url,
            "source_node": source_node,
            "task": action,
            "params": data
        }

        async with self.lock:
            message_json = json.dumps(message)
            logger.info(f"Sending message: {message_json}")
            await websocket.send(message_json)

            response = await websocket.recv()
            logger.info(f"Received raw response: {response}")

        if isinstance(response, str):
            response_data = json.loads(response)
            logger.info(f"Received response: {response_data}")
        else:
            logger.error(f"Received non-string response: {response}")
            raise Exception("Received non-string response")

        return response_data['params']

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

    async def close(self):
        if self.websocket:
            await self.websocket.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()