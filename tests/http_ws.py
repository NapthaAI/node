import unittest
import os
import io
import uuid
import json
import shutil
import zipfile
import asyncio
import httpx
import logging
import aiofiles

def get_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger

logger = get_logger()

HTTPX_TIMEOUT = 60

class TestHTTPServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.base_url = "http://localhost:7001"
        cls.public_key = uuid.uuid4().hex
        cls.consumer_id = None
        cls.folder_id = None
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
    def tearDownClass(cls):
        # Clean up the output directory
        if os.path.exists(cls.output_dir):
            shutil.rmtree(cls.output_dir)
        logger.info(f"Cleaned up test output directory: {cls.output_dir}")

        # Close the event loop
        cls.loop.close()
        logger.info("Closed the event loop")

    @classmethod
    async def register_user(cls):
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            response = await client.post(f"{cls.base_url}/user/register", json={"public_key": cls.public_key})
            logger.debug(f"User register response: {response.json()}")
            logger.debug(f"User register response status: {response.status_code}")
            assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}"
            assert "id" in response.json(), "Expected 'id' in response JSON"
            cls.consumer_id = response.json()['id']
            logger.debug(f"Registered user ID: {cls.consumer_id}")

    def test_01_check_user(self):
        async def check_user():
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                response = await client.post(f"{self.base_url}/user/check", json={"public_key": self.public_key})
                logger.debug(f"Check user response: {response.json()}")
                self.assertEqual(response.status_code, 200)
                self.assertIn("id", response.json())
                logger.debug(f"Expected user ID: {self.consumer_id}")
                logger.debug(f"Received user ID: {response.json()['id']}")
                self.assertEqual(response.json()["id"], self.consumer_id)
                self.assertTrue(response.json()["is_registered"])

        self.loop.run_until_complete(check_user())

    def test_02_no_user(self):
        async def check_user():
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                response = await client.post(f"{self.base_url}/user/check", json={"public_key": "no_user"})
                logger.debug(f"Check no user response: {response.json()}")
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()["is_registered"])

        self.loop.run_until_complete(check_user())

    def test_03_run_agent(self):
        async def run_agent():
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                agent_run_input = {
                    'consumer_id': self.consumer_id,
                    "inputs": {"firstname": "hello", "surname": "world"},
                    "agent_deployment": {
                        'name': 'hello_world_agent',
                        'module': {'name': 'hello_world_agent'},
                        'agent_node_url': '',
                        'agent_config': {}
                    },
                }
                self.response = await client.post(f"{self.base_url}/agent/run", json=agent_run_input)
                logger.debug(f"Run agent response: {self.response.json()}")
                self.assertEqual(self.response.status_code, 200)
                self.assertIn("id", self.response.json())

        self.loop.run_until_complete(run_agent())

        async def check_agent():
            while True:
                async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                    response = await client.post(f"{self.base_url}/agent/check", json=self.response.json())
                    logger.debug(f"Check agent response: {response.json()}")
                    self.assertEqual(response.status_code, 200)
                    if response.json()["status"] == "completed":
                        break
                    elif response.json()["status"] == "error":
                        # fail the test
                        self.fail(f"Agent error: {response.json()['error']}")
                    await asyncio.sleep(1)

            results = response.json()["results"]
            logger.debug(f"Agent results: {results}")
            self.assertEqual(results[0], "Hello hello world")

        self.loop.run_until_complete(check_agent())

    def test_04_write_read_storage(self):
        async def write_read_storage():
            # Write to storage
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                with open(self.test_file_path, 'rb') as f:
                    files = {'file': ('img.png', f, 'image/png')}
                    response = await client.post(f"{self.base_url}/storage/write", files=files)
                logger.debug(f"Write storage response: {response.json()}")
                self.assertEqual(response.status_code, 201)  # Assuming 201 for successful creation
                self.assertIn("folder_id", response.json())
                folder_id = response.json()["folder_id"]
                TestHTTPServer.folder_id = response.json()["folder_id"]
                logger.debug(f"Set folder_id to: {TestHTTPServer.folder_id}")

            # Read from storage
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                response = await client.get(f"{self.base_url}/storage/read/{folder_id}")
                logger.debug(f"Read storage response status: {response.status_code}")
                self.assertEqual(response.status_code, 200)

            # Process the ZIP content
            zip_content = io.BytesIO(response.content)
            with zipfile.ZipFile(zip_content) as zip_file:
                file_list = zip_file.namelist()
                logger.debug(f"Files in ZIP: {file_list}")
                
                # Assuming the image is the first file in the ZIP
                if not file_list:
                    self.fail("No files found in the ZIP archive")
                
                image_file_name = file_list[0]
                extracted_content = zip_file.read(image_file_name)

            # Save the extracted content
            extracted_image_path = os.path.join(self.output_dir, "extracted_img.png")
            with open(extracted_image_path, 'wb') as f:
                f.write(extracted_content)

            # Compare the first 100 bytes of both files
            with open(self.test_file_path, 'rb') as f1, open(extracted_image_path, 'rb') as f2:
                original_start = f1.read(100)
                received_start = f2.read(100)
                
            self.assertEqual(original_start, received_start, "First 100 bytes of files do not match")
            
            logger.debug(f"Original file first 100 bytes: {original_start}")
            logger.debug(f"Received file first 100 bytes: {received_start}")

            # Log file sizes for information
            original_size = os.path.getsize(self.test_file_path)
            received_size = os.path.getsize(extracted_image_path)
            logger.debug(f"Original file size: {original_size}")
            logger.debug(f"Received file size: {received_size}")

            # Clean up
            os.remove(extracted_image_path)

        self.loop.run_until_complete(write_read_storage())

    def test_05_write_read_ipfs(self):
        async def write_read_ipfs():
            # Write to IPFS
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                with open(self.test_file_path, 'rb') as f:
                    files = {'file': ('img.png', f, 'image/png')}
                    data = {
                        'publish_to_ipns': 'true',
                        'update_ipns_name': None
                    }
                    response = await client.post(f"{self.base_url}/storage/write_ipfs", files=files, data=data)
                
                logger.debug(f"Write IPFS response: {response.json()}")
                self.assertEqual(response.status_code, 201)
                self.assertIn("ipfs_hash", response.json())
                self.assertIn("ipns_hash", response.json())
                ipfs_hash = response.json()["ipfs_hash"]

            # Read from IPFS
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                response = await client.get(f"{self.base_url}/storage/read_ipfs/{ipfs_hash}")
                logger.debug(f"Read IPFS response status: {response.status_code}")
                self.assertEqual(response.status_code, 200)

                content_type = response.headers.get('content-type', '')
                logger.debug(f"Content-Type: {content_type}")

                if 'application/zip' in content_type:
                    # Handle zipped content
                    zip_content = io.BytesIO(response.content)
                    with zipfile.ZipFile(zip_content) as zip_file:
                        file_list = zip_file.namelist()
                        logger.debug(f"Files in ZIP: {file_list}")
                        
                        if not file_list:
                            self.fail("No files found in the ZIP archive")
                        
                        image_file_name = next((name for name in file_list if name.endswith('.png')), None)
                        if not image_file_name:
                            self.fail("No PNG file found in the ZIP archive")
                        
                        extracted_content = zip_file.read(image_file_name)
                else:
                    # Handle single file content
                    extracted_content = response.content

            # Save the extracted content
            extracted_image_path = os.path.join(self.output_dir, "ipfs_extracted_img.png")
            async with aiofiles.open(extracted_image_path, 'wb') as f:
                await f.write(extracted_content)

            # Compare the first 100 bytes of both files
            with open(self.test_file_path, 'rb') as f1, open(extracted_image_path, 'rb') as f2:
                original_start = f1.read(100)
                received_start = f2.read(100)
                
            self.assertEqual(original_start, received_start, "First 100 bytes of files do not match")
            
            logger.debug(f"Original file first 100 bytes: {original_start}")
            logger.debug(f"Received file first 100 bytes: {received_start}")

            # Log file sizes for information
            original_size = os.path.getsize(self.test_file_path)
            received_size = os.path.getsize(extracted_image_path)
            logger.debug(f"Original file size: {original_size}")
            logger.debug(f"Received file size: {received_size}")

            # Clean up
            os.remove(extracted_image_path)

        self.loop.run_until_complete(write_read_ipfs())

    def test_06_generate_image(self):
        async def generate_image():
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                agent_run_input = {
                    'consumer_id': self.consumer_id,
                    "inputs": {"prompt": "A beautiful image of a sunset over a calm ocean"},
                    "agent_deployment": {
                        'name': 'generate_image',
                        'module': {'name': 'generate_image'},
                        'agent_node_url': '',
                        'agent_config': {}
                    },
                }
                self.response = await client.post(f"{self.base_url}/agent/run", json=agent_run_input)
                logger.debug(f"Generate image response: {self.response.json()}")
                self.assertEqual(self.response.status_code, 200)
                self.assertIn("id", self.response.json())

        self.loop.run_until_complete(generate_image())

        async def check_generate_image():
            while True:
                async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                    response = await client.post(f"{self.base_url}/agent/check", json=self.response.json())
                    logger.debug(f"Check generate image response: {response.json()}")
                    self.assertEqual(response.status_code, 200)
                    if response.json()["status"] == "completed":
                        break
                    elif response.json()["status"] == "error":
                        self.fail(f"Agent error: {response.json()['error']}")
                    await asyncio.sleep(1)

            results = response.json()["results"]
            logger.debug(f"Agent results: {results}")
            self.assertIn("Image saved to", results[0])

        self.loop.run_until_complete(check_generate_image())

    def test_07_image_to_image(self):
        async def image_to_image():
            logger.debug(f"Folder ID: {self.folder_id}")
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                agent_run_input = {
                    'consumer_id': self.consumer_id,
                    "inputs": {
                        "prompt": "A beautiful image of a sunset over a calm ocean",
                        "input_dir": self.folder_id
                    },
                    "agent_deployment": {
                        'name': 'image_to_image',
                        'module': {'name': 'image_to_image'},
                        'agent_node_url': '',
                        'agent_config': {}
                    },
                }
                self.response = await client.post(f"{self.base_url}/agent/run", json=agent_run_input)
                logger.debug(f"Image to image response: {self.response.json()}")
                self.assertEqual(self.response.status_code, 200)
                self.assertIn("id", self.response.json())

        self.loop.run_until_complete(image_to_image())

        async def check_image_to_image():
            while True:
                async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                    response = await client.post(f"{self.base_url}/agent/check", json=self.response.json())
                    logger.debug(f"Check image to image response: {response.json()}")
                    self.assertEqual(response.status_code, 200)
                    if response.json()["status"] == "completed":
                        break
                    elif response.json()["status"] == "error":
                        self.fail(f"Agent error: {response.json()['error']}")
                    await asyncio.sleep(1)

            results = response.json()["results"]
            logger.debug(f"Agent results: {results}")
            self.assertIn("Image saved to", results[0])

        self.loop.run_until_complete(check_image_to_image())

    def test_simple_chat_agent(self):
        async def simple_chat_agent():
            agent_run_input = {
                'consumer_id': self.consumer_id,
                "inputs": {"tool_name": "chat", "tool_input_data": "what is the weather in tokyo?"},
                "agent_deployment": {
                    'name': 'simple_chat_agent',
                    'module': {'name': 'simple_chat_agent'},
                    'agent_node_url': '',
                    'agent_config': {}
                },
            }

            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                self.response = await client.post(f"{self.base_url}/agent/run", json=agent_run_input)
                logger.debug(f"Simple chat agent response: {self.response.json()}")
                self.assertEqual(self.response.status_code, 200)
                self.assertIn("id", self.response.json())

        self.loop.run_until_complete(simple_chat_agent())

        async def check_simple_chat_agent():
            while True:
                async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                    response = await client.post(f"{self.base_url}/agent/check", json=self.response.json())
                    logger.debug(f"Check simple chat agent response: {response.json()}")
                    self.assertEqual(response.status_code, 200)
                    if response.json()["status"] == "completed":
                        break
                    elif response.json()["status"] == "error":
                        self.fail(f"Agent error: {response.json()['error']}")
                    await asyncio.sleep(1)

            results = json.loads(response.json()["results"][0])
            logger.debug(f"Agent results: {results[0]}")
            self.assertIn(results[0]['role'], 'system')

        self.loop.run_until_complete(check_simple_chat_agent())

    def test_08_multiagent_chat(self):
        async def multiagent_chat():
            orchestrator_run_input = {
                'consumer_id': self.consumer_id,
                "inputs": {"prompt": "lets count to 20. I will start. one"},
                "orchestrator_deployment": {
                    'name': 'multiagent_chat',
                    'module': {'name': 'multiagent_chat'},
                    'orchestrator_node_url': self.base_url,
                    'agent_deployments': [
                        {'agent_node_url': 'ws://localhost:7002'},
                        {'agent_node_url': 'ws://localhost:7002'}
                    ],
                    'environment_deployments': [{'environment_node_url': 'http://localhost:7001'}]
                },
            }

            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                self.response = await client.post(f"{self.base_url}/orchestrator/run", json=orchestrator_run_input)
                logger.debug(f"Multiagent chat response: {self.response.json()}")
                self.assertEqual(self.response.status_code, 200)
                self.assertIn("id", self.response.json())

        self.loop.run_until_complete(multiagent_chat())

        async def check_multiagent_chat():
            while True:
                async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                    response = await client.post(f"{self.base_url}/orchestrator/check", json=self.response.json())
                    logger.debug(f"Check multiagent chat response: {response.json()}")
                    self.assertEqual(response.status_code, 200)
                    if response.json()["status"] == "completed":
                        break
                    elif response.json()["status"] == "error":
                        self.fail(f"Orchestrator error: {response.json()['error']}")
                    await asyncio.sleep(1)

            results = response.json()["results"]
            self.assertTrue(results)

            # get id 
            id_ = response.json()["id"]

            # get the row from the local db
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                response = await client.get(f"{self.base_url}/local-db/table/multi_chat_simulations/rows", params={"id": id_})
                logger.debug(f"Local db response: {response.json()}")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json())

        self.loop.run_until_complete(check_multiagent_chat())

    def test_09_random_number_agent(self):
        async def random_number_agent():
            agent_run_input = {
                'consumer_id': self.consumer_id,
                "inputs": {"agent_name": "random_number"},
                "agent_deployment": {
                    'name': 'random_number_agent',
                    'module': {'name': 'random_number_agent'},
                    'agent_node_url': '',
                    'agent_config': {}
                },
            }

            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                self.response = await client.post(f"{self.base_url}/agent/run", json=agent_run_input)
                logger.debug(f"Random number agent response: {self.response.json()}")
                self.assertEqual(self.response.status_code, 200)
                self.assertIn("id", self.response.json())

        self.loop.run_until_complete(random_number_agent())

        async def check_random_number_agent():
            while True:
                async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                    response = await client.post(f"{self.base_url}/agent/check", json=self.response.json())
                    logger.debug(f"Check random number agent response: {response.json()}")
                    self.assertEqual(response.status_code, 200)
                    if response.json()["status"] == "completed":
                        break
                    elif response.json()["status"] == "error":
                        self.fail(f"Agent error: {response.json()['error']}")
                    await asyncio.sleep(1)

            results = response.json()["results"]
            logger.debug(f"Agent results: {results}")
            self.assertIsInstance(int(results[0]), int)

        self.loop.run_until_complete(check_random_number_agent())

    def test_10_keynesian_beauty_contest(self):
        async def keynesian_beauty_contest():
            orchestrator_run_input = {
                'consumer_id': self.consumer_id,
                "inputs": {"num_agents": 3},
                "orchestrator_deployment": {
                    'name': 'keynesian_beauty_contest',
                    'module': {'name': 'keynesian_beauty_contest'},
                    'orchestrator_node_url': self.base_url,
                    'agent_deployments': [{'agent_node_url': 'ws://localhost:7002'} for _ in range(2)],
                    'environment_deployments': [{'environment_node_url': 'http://localhost:7001'}]
                },
            }

            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                self.response = await client.post(f"{self.base_url}/orchestrator/run", json=orchestrator_run_input)
                logger.debug(f"Keynesian beauty contest response: {self.response.json()}")
                self.assertEqual(self.response.status_code, 200)
                self.assertIn("id", self.response.json())

        self.loop.run_until_complete(keynesian_beauty_contest())

        async def check_keynesian_beauty_contest():
            while True:
                async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                    response = await client.post(f"{self.base_url}/orchestrator/check", json=self.response.json())
                    logger.debug(f"Check keynesian beauty contest response: {response.json()}")
                    self.assertEqual(response.status_code, 200)
                    if response.json()["status"] == "completed":
                        break
                    elif response.json()["status"] == "error":
                        self.fail(f"Orchestrator error: {response.json()['error']}")
                    await asyncio.sleep(1)

            results = response.json()["results"]
            logger.debug(f"Orchestrator results: {results}")
            results = json.loads(results[0])
            self.assertEqual(len(results), 3)

        self.loop.run_until_complete(check_keynesian_beauty_contest())

    def test_11_test_personas(self):
        async def test_personas():
            agent_run_input = {
                'consumer_id': self.consumer_id,
                "inputs": {"question": "is the price of bitcoin going up?", "num_personas": 2},
                "agent_deployment": {
                    'name': 'test_personas',
                    'module': {'name': 'test_personas'},
                    'agent_node_url': '',
                    'agent_config': {}
                },
            }

            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                self.response = await client.post(f"{self.base_url}/agent/run", json=agent_run_input)
                logger.debug(f"Test personas response: {self.response.json()}")
                self.assertEqual(self.response.status_code, 200)
                self.assertIn("id", self.response.json())

        self.loop.run_until_complete(test_personas())

        async def check_test_personas():
            while True:
                async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                    response = await client.post(f"{self.base_url}/agent/check", json=self.response.json())
                    logger.debug(f"Check test personas response: {response.json()}")
                    self.assertEqual(response.status_code, 200)
                    if response.json()["status"] == "completed":
                        break
                    elif response.json()["status"] == "error":
                        self.fail(f"Agent error: {response.json()['error']}")
                    await asyncio.sleep(1)

            results = response.json()["results"]
            logger.debug(f"Agent results: {results}")
            self.assertTrue(results[0])

        self.loop.run_until_complete(check_test_personas())

if __name__ == '__main__':
    unittest.main(failfast=False)