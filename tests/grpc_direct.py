import unittest
import os
import json
import uuid
import shutil
import asyncio
import logging
from google.protobuf.struct_pb2 import Struct
from google.protobuf.json_format import MessageToDict
import grpc
from grpc_stuffs import grpc_server_pb2_grpc, grpc_server_pb2

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

class TestGRPCServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.base_url = "localhost:7001"
        cls.public_key = uuid.uuid4().hex
        cls.consumer_id = None
        cls.output_dir = "./test_output"
        os.makedirs(cls.output_dir, exist_ok=True)

        # Create a new event loop
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)

        # Create a gRPC channel and stub
        cls.channel = grpc.aio.insecure_channel(cls.base_url)
        cls.stub = grpc_server_pb2_grpc.GrpcServerStub(cls.channel)

        # Register user and set consumer_id
        cls.loop.run_until_complete(cls.register_user())

    @classmethod
    def tearDownClass(cls):
        # Clean up the output directory
        if os.path.exists(cls.output_dir):
            shutil.rmtree(cls.output_dir)
        logger.info(f"Cleaned up test output directory: {cls.output_dir}")

        # Close the gRPC channel
        cls.loop.run_until_complete(cls.channel.close())

        # Close the event loop
        cls.loop.close()
        logger.info("Closed the event loop and gRPC channel")

    @classmethod
    async def register_user(cls):
        response = await cls.stub.RegisterUser(grpc_server_pb2.RegisterUserRequest(public_key=cls.public_key))
        logger.debug(f"User register response: {response}")
        cls.consumer_id = response.id
        logger.debug(f"Registered user ID: {cls.consumer_id}")

    def test_check_user(self):
        async def check_user():
            response = await self.stub.CheckUser(grpc_server_pb2.CheckUserRequest(public_key=self.public_key))
            logger.debug(f"Check user response: {response}")
            self.assertTrue(response.is_registered)
            self.assertEqual(response.id, self.consumer_id)

        self.loop.run_until_complete(check_user())

    def test_no_user(self):
        async def check_user():
            response = await self.stub.CheckUser(grpc_server_pb2.CheckUserRequest(public_key="no_user"))
            logger.debug(f"Check no user response: {response}")
            self.assertFalse(response.is_registered)

        self.loop.run_until_complete(check_user())

    def test_run_agent(self):
        async def run_agent():
            agent_run_params = Struct()
            agent_run_params.fields['firstname'].string_value = 'hello'
            agent_run_params.fields['surname'].string_value = 'world'

            request = grpc_server_pb2.RunAgentRequest(
                agent_name="hello_world_agent",
                consumer_id=self.consumer_id,
                agent_run_params=agent_run_params
            )
            
            try:
                async for response in self.stub.RunAgent(request):
                    logger.debug(f"Received update: Status = {response.status}")
                    if response.status == 'completed':
                        logger.debug("Agent run completed.")
                        logger.debug(f"Results: {response.results}")
                        self.assertIsNotNone(response.id)
                        self.assertEqual(response.status, 'completed')
                        self.assertTrue(len(response.results) > 0)
                        expected_results = ['Hello hello world']
                        self.assertEqual(response.results, expected_results)
                        return  # Exit the function once we get a 'completed' status
                    elif response.status == 'error':
                        logger.error(f"Error occurred: {response.error_message}")
                        self.fail(f"Agent run failed with error: {response.error_message}")
                    elif response.status == 'running':
                        logger.debug("Agent is still running...")
                    else:
                        logger.warning(f"Unexpected status: {response.status}")

                # If we exit the loop without returning, it means we didn't get a 'completed' status
                self.fail("Agent run did not complete successfully")

            except grpc.RpcError as e:
                logger.error(f"RPC error: {e.code()}, {e.details()}")
                self.fail(f"RPC error occurred: {e.details()}")

        self.loop.run_until_complete(run_agent())

    def test_run_multi_agent(self):
        async def run_multi_agent():
            agent_run_params = Struct()
            agent_run_params.fields['num_agents'].number_value = 5

            request = grpc_server_pb2.RunAgentRequest(
                agent_name="keynesian_beauty_contest",
                consumer_id=self.consumer_id,
                agent_run_params=agent_run_params,
                worker_nodes=["localhost:7001"]
            )

            try:
                async for response in self.stub.RunAgent(request):
                    logger.debug(f"Received update: Status = {response.status}")
                    if response.status == 'completed':
                        logger.debug("Agent run completed.")
                        logger.debug(f"Results: {response.results}")
                        self.assertIsNotNone(response.id)
                        self.assertEqual(response.status, 'completed')
                        self.assertTrue(len(response.results) > 0)
                        results = response.results
                        results = json.loads(results[0])
                        self.assertEqual(len(results), 5)
                        return  # Exit the function once we get a 'completed' status
                    elif response.status == 'error':
                        logger.error(f"Error occurred: {response.error_message}")
                        self.fail(f"Agent run failed with error: {response.error_message}")
                    elif response.status == 'running':
                        logger.debug("Agent is still running...")
                    elif response.status == 'started':
                        logger.debug("Agent run started.")
                    else:
                        logger.warning(f"Unexpected status: {response.status}")

                # If we exit the loop without returning, it means we didn't get a 'completed' status
                self.fail("Agent run did not complete successfully")

            except grpc.RpcError as e:
                logger.error(f"RPC error: {e.code()}, {e.details()}")
                self.fail(f"RPC error occurred: {e.details()}")

        self.loop.run_until_complete(run_multi_agent())

if __name__ == '__main__':
    unittest.main(failfast=False)