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

    def test_check_user(self):
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

    def test_no_user(self):
        async def check_user():
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                response = await client.post(f"{self.base_url}/user/check", json={"public_key": "no_user"})
                logger.debug(f"Check no user response: {response.json()}")
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()["is_registered"])

        self.loop.run_until_complete(check_user())

    def test_run_agent(self):
        async def run_agent():
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                params = {
                    "agent_name": "hello_world_agent",
                    "agent_run_params": {"firstname": "hellish", "surname": "world"},
                    "consumer_id": self.consumer_id,
                }
                self.response = await client.post(f"{self.base_url}/agent/run", json=params)
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

        self.loop.run_until_complete(check_agent())

    def test_run_multi_agent(self):
        async def run_multi_agent():
            async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                params = {
                    "agent_name": "keynesian_beauty_contest",
                    "agent_run_params": {"num_agents": 5},
                    "consumer_id": self.consumer_id,
                    "worker_nodes": ["http://localhost:7001"]
                }

                self.response = await client.post(f"{self.base_url}/agent/run", json=params)
                logger.debug(f"Run multi agent response: {self.response.json()}")
                self.assertEqual(self.response.status_code, 200)
                self.assertIn("id", self.response.json())

        self.loop.run_until_complete(run_multi_agent())

        async def check_multi_agent():
            while True:
                async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
                    response = await client.post(f"{self.base_url}/agent/check", json=self.response.json())
                    logger.debug(f"Check multi agent response: {response.json()}")
                    self.assertEqual(response.status_code, 200)
                    if response.json()["status"] == "completed":
                        break
                    elif response.json()["status"] == "error":
                        # fail the test
                        self.fail(f"Agent error: {response.json()['error']}")
                    await asyncio.sleep(3)

            if response.json()["status"] == "completed":
                results = response.json()["results"][0]
                logger.debug(f"Results: {results}")
                results = json.loads(results)
                logger.debug(f"Results: {results}")
                self.assertEqual(len(results), 5)
            else:
                self.fail(f"Agent error: {response.json()['error_message']}")

        self.loop.run_until_complete(check_multi_agent())

    def test_write_read_storage(self):
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

    def test_write_read_ipfs(self):
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

if __name__ == '__main__':
    unittest.main(failfast=False)