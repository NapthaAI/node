import unittest
import asyncio
import websockets
import json
import os
import base64
import uuid
import shutil
import zipfile
import logging


def get_logger():
    logger = logging.getLogger(__name__)
    # Set the logging level to DEBUG
    logger.setLevel(logging.DEBUG)
    # Create a console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    # Create a formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger

logger = get_logger()

class TestHubFunctionality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_url = "ws://localhost:7001/ws"
        cls.client_id = "client_123"
        cls.public_key = uuid.uuid4().hex
        cls.consumer_id = None
        cls.test_file_path = "./img.png"
        cls.output_dir = "./test_output"
        cls.chunk_size = 256 * 1024  # 256 KB chunks
        os.makedirs(cls.output_dir, exist_ok=True)

        # Create a new event loop
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)

        # Register user and set consumer_id
        cls.loop.run_until_complete(cls.register_user())

    @classmethod
    async def register_user(cls):
        try:
            uri = f"{cls.base_url}/register_user/{cls.client_id}"
            logger.debug(f"Attempting to connect to {uri}")
            async with websockets.connect(uri) as websocket:
                params = {"public_key": cls.public_key}
                logger.debug(f"Sending params: {params}")
                await websocket.send(json.dumps(params))
                logger.debug("Waiting for response...")
                response = await websocket.recv()
                logger.debug(f"Received response: {response}")
                response_data = json.loads(response)
                if 'id' in response_data:
                    cls.consumer_id = response_data['id']
                    logger.debug(f"Registered user with consumer_id: {cls.consumer_id}")
                else:
                    raise Exception(f"Failed to register user: {response_data}")
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"WebSocket connection closed unexpectedly: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response: {e}")
            logger.error(f"Raw response: {response}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during user registration: {str(e)}")
            raise

    async def async_test(self, coro):
        return await coro

    def test_check_user(self):
        async def check_user():
            uri = f"{self.base_url}/check_user/{self.client_id}"
            async with websockets.connect(uri) as websocket:
                params = {"public_key": self.public_key}
                await websocket.send(json.dumps(params))
                response = await websocket.recv()
                response_data = json.loads(response)
                logger.debug(f"Check user response data: {response_data}")
                self.assertIn("id", response_data)
                self.assertEqual(response_data["id"], self.consumer_id)

        self.loop.run_until_complete(self.async_test(check_user()))

    def test_check_user_not_found(self):
        async def check_user_not_found():
            uri = f"{self.base_url}/check_user/{self.client_id}"
            async with websockets.connect(uri) as websocket:
                params = {"public_key": "wrong_public_key"}
                await websocket.send(json.dumps(params))
                response = await websocket.recv()
                response_data = json.loads(response)
                logger.debug(f"Check user response data: {response_data}")
                self.assertEqual(response_data['is_registered'],False)

        self.loop.run_until_complete(self.async_test(check_user_not_found()))

    def test_run_agent(self):
        async def run_agent():
            uri = f"{self.base_url}/run_agent/{self.client_id}"
            async with websockets.connect(uri) as websocket:
                params = {
                    "agent_name": "hello_world_agent",
                    "agent_run_params": {"firstname": "hellish", "surname": "world"},
                    "consumer_id": self.consumer_id,
                }
                await websocket.send(json.dumps(params))
                response = await websocket.recv()
                response_data = json.loads(response)
                logger.debug(f"Run agent response data: {response_data}")
                expected_result =  ['Hello hellish world']
                self.assertEqual(response_data["data"]["results"], expected_result)
                
        asyncio.get_event_loop().run_until_complete(self.async_test(run_agent()))

    def test_run_multi_agent(self):
        async def run_multi_agent():
            uri = f"{self.base_url}/run_agent/{self.client_id}"
            async with websockets.connect(uri) as websocket:
                params = {
                    "agent_name": "keynesian_beauty_contest",
                    "agent_run_params": {"num_agents": 5},
                    "consumer_id": self.consumer_id,
                    "worker_nodes": ["ws://localhost:7001"]
                }

                await websocket.send(json.dumps(params))
                response = await websocket.recv()
                response_data = json.loads(response)
                logger.debug(f"Run multi agent response data: {response_data}")

                results = response_data["data"]["results"][0]
                logger.debug(f"Results: {results}")
                results = json.loads(results)
                logger.debug(f"Results: {results}")
                self.assertEqual(len(results), 5)

        asyncio.get_event_loop().run_until_complete(self.async_test(run_multi_agent()))

    def test_write_and_read_storage(self):
        async def write_and_read_storage():
            # Write to storage
            uri = f"{self.base_url}/write_storage/{self.client_id}"
            folder_id = None
            async with websockets.connect(uri) as websocket:
                with open(self.test_file_path, "rb") as file:
                    file_name = os.path.basename(self.test_file_path)
                    chunk_index = 0
                    while True:
                        chunk = file.read(self.chunk_size)
                        if not chunk:
                            break
                        
                        encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                        message = {
                            "filename": file_name,
                            "file_data": encoded_chunk,
                        }
                        await websocket.send(json.dumps(message))
                        response = await websocket.recv()
                        response_data = json.loads(response)
                        logger.debug(f"Write chunk {chunk_index}")
                        if "folder_id" in response_data:
                            folder_id = response_data["folder_id"]
                        chunk_index += 1

                # Send EOF message
                eof_message = {
                    "filename": file_name,
                    "file_data": "EOF",
                }
                await websocket.send(json.dumps(eof_message))
                final_response = await websocket.recv()                
                final_response_data = json.loads(final_response)

                # assert message == "Files written to storage"  
                message = final_response_data['data']['message']

                # assert message == "Files written to storage"
                self.assertEqual(message, "Files written to storage")

                # assert folder_id is not None
                folder_id = final_response_data['data']['folder_id']
                self.assertIsNotNone(folder_id, "Failed to get folder_id from write operation")

            # Read from storage
            uri = f"{self.base_url}/read_storage/{self.client_id}"
            async with websockets.connect(uri) as websocket:
                message = {"folder_id": folder_id, "consumer_id": self.consumer_id}
                await websocket.send(json.dumps(message))
                
                temp_zip = os.path.join(self.output_dir, "temp_file.zip")
                with open(temp_zip, "wb") as output_file:
                    while True:
                        response = await websocket.recv()
                        response_data = json.loads(response)
                        
                        if response_data.get("status") == "error":
                            raise Exception(f"Error from server: {response_data.get('message')}")
                        
                        file_data = response_data["data"]["file_data"]
                        if file_data == "EOF":
                            break
                        
                        chunk = base64.b64decode(file_data)
                        output_file.write(chunk)

            # Extract the zip file
            with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                zip_ref.extractall(self.output_dir)

            # Find the extracted file
            extracted_files = os.listdir(self.output_dir)
            extracted_file = next((f for f in extracted_files if f != "temp_file.zip"), None)
            if not extracted_file:
                raise Exception("No file found in the extracted content")

            extracted_file_path = os.path.join(self.output_dir, extracted_file)

            # Compare original and retrieved files
            with open(self.test_file_path, "rb") as original_file, open(extracted_file_path, "rb") as retrieved_file:
                original_content = original_file.read()
                retrieved_content = retrieved_file.read()
                
                logger.debug(f"First 100 bytes of original: {original_content[:100]}")
                logger.debug(f"First 100 bytes of retrieved: {retrieved_content[:100]}")
                    
                self.assertEqual(original_content[:100], retrieved_content[:100], "Retrieved file content doesn't match original")

        asyncio.get_event_loop().run_until_complete(self.async_test(write_and_read_storage()))

    def test_write_and_read_ipfs(self):
        async def write_and_read_ipfs():
            # Write to IPFS
            uri = f"{self.base_url}/write_ipfs/{self.client_id}"
            ipfs_hash = None
            
            async with websockets.connect(uri) as websocket:
                file_name = os.path.basename(self.test_file_path)
                with open(self.test_file_path, "rb") as file:
                    chunk_index = 0
                    while True:
                        chunk = file.read(self.chunk_size)
                        if not chunk:
                            break
                        
                        encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                        message = {
                            "filename": file_name,
                            "file_data": encoded_chunk,
                            "publish_to_ipns": True,
                            "consumer_id": self.consumer_id
                        }
                        await websocket.send(json.dumps(message))
                        response = await websocket.recv()
                        response_data = json.loads(response)
                        logger.debug(f"Write chunk {chunk_index} response: {response_data}")
                        chunk_index += 1

                # Send EOF message
                eof_message = {
                    "filename": file_name,
                    "file_data": "EOF",
                    "publish_to_ipns": True,
                }
                await websocket.send(json.dumps(eof_message))
                final_response = await websocket.recv()
                final_response_data = json.loads(final_response)
                logger.debug(f"Final IPFS write response: {final_response_data}")
                
                message = final_response_data['data']['message']
                ipfs_hash = final_response_data['data']['ipfs_hash']
                ipns_hash = final_response_data['data']['ipns_hash']
                self.assertEqual(message, "File written and pinned to IPFS and published to IPNS and published to IPNS")
                self.assertIsNotNone(ipfs_hash, "Failed to get IPFS hash from write operation")
                self.assertIsNotNone(ipns_hash, "Failed to get IPNS hash from write operation")

            # Read from IPFS
            uri = f"{self.base_url}/read_ipfs/{self.client_id}"
            async with websockets.connect(uri) as websocket:
                message = {"hash_or_name": ipfs_hash, "consumer_id": self.consumer_id}
                await websocket.send(json.dumps(message))
                
                temp_file = os.path.join(self.output_dir, "temp_file")
                with open(temp_file, "wb") as output_file:
                    while True:
                        response = await websocket.recv()
                        response_data = json.loads(response)
                        
                        if response_data.get("status") == "error":
                            raise Exception(f"Error from server: {response_data.get('message')}")
                        
                        file_data = response_data["data"]["file_data"]
                        if file_data == "EOF":
                            break
                        
                        chunk = base64.b64decode(file_data)
                        output_file.write(chunk)

            # Compare original and retrieved files
            with open(self.test_file_path, "rb") as original_file, open(temp_file, "rb") as retrieved_file:
                original_content = original_file.read()
                retrieved_content = retrieved_file.read()
                
                logger.info(f"Original file size: {len(original_content)} bytes")
                logger.info(f"Retrieved file size: {len(retrieved_content)} bytes")
                logger.debug(f"First 100 bytes of original: {original_content[:100]}")
                logger.debug(f"First 100 bytes of retrieved: {retrieved_content[:100]}")
                
                self.assertEqual(original_content[:100], retrieved_content[:100], "Retrieved file content doesn't match original")

        asyncio.get_event_loop().run_until_complete(self.async_test(write_and_read_ipfs()))

    def test_random_number_protocol(self):
        pass

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.output_dir, ignore_errors=True)

if __name__ == '__main__':
    unittest.main()