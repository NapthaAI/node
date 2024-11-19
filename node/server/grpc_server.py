import os
import asyncio
import grpc
import signal
import logging
from datetime import datetime
from google.protobuf.empty_pb2 import Empty
from grpc import ServicerContext

from node.schemas import AgentRunInput, DockerParams
from node.storage.db.db import DB
from node.storage.hub.hub import Hub
from node.user import register_user, check_user
from node.worker.docker_worker import execute_docker_agent
from node.worker.template_worker import run_agent, run_orchestrator
from node.server import grpc_server_pb2, grpc_server_pb2_grpc

logger = logging.getLogger(__name__)


class GrpcServerServicer(grpc_server_pb2_grpc.GrpcServerServicer):
    async def CheckUser(self, request, context):
        logger.info(f"Checking user: {request.public_key}")
        input_data = {"public_key": request.public_key}

        _, user_data = await check_user(input_data)
        logger.info(f"User check result: {user_data}")
        return grpc_server_pb2.CheckUserResponse(**user_data)


    async def RegisterUser(self, request, context):
        logger.info(f"Registering user: {request.public_key}")
        input_data = {"public_key": request.public_key}
        logger.info(f"Registering user: {input_data}")
        
        # Unpack the result tuple to get the success flag and data dictionary separately
        success, user_data = await register_user(input_data)
        
        if success:
            logger.info(f"User registration result: {user_data}")
            return grpc_server_pb2.RegisterUserResponse(**user_data)
        else:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details('User registration failed')
            return grpc_server_pb2.RegisterUserResponse()

    async def RunAgent(self, request, context):
        try:
            logger.info(f"Running agent: {request.agent_name}")
            input_data = {
                "agent_name": request.agent_name,
                "consumer_id": request.consumer_id,
                "agent_run_params": request.agent_run_params,
                "agent_type": request.agent_type,
                "worker_nodes": request.worker_nodes,
                "personas_urls": request.personas_urls,
            }

            agent_run_input = AgentRunInput(**input_data)

            async with Hub() as hub:
                success, user, user_id = await hub.signin(
                    os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                )
                agent = await hub.list_agents(f"agent:{agent_run_input.agent_name}")
                logger.info(f"Found agent: {agent}")

                if not agent:
                    yield grpc_server_pb2.RunAgentResponse(
                        status="error",
                        error_message="Agent not found",
                        agent_name=request.agent_name,
                        consumer_id=request.consumer_id,
                        agent_run_type=request.agent_type,
                        id="",
                        results=[],
                        worker_nodes=[],
                    )
                    return

                agent_run_input.agent_run_type = agent["type"]
                agent_run_input.agent_version = agent["version"]
                agent_run_input.agent_source_url = agent["url"]
                if agent_run_input.personas_urls is None:
                    if 'personas_urls' in agent:
                        agent_run_input.personas_urls = agent["personas_urls"]
                else:
                    if 'personas_urls' in agent:
                        agent_run_input.personas_urls.extend(agent["personas_urls"])

                if agent["type"] == "docker":
                    agent_run_input.agent_run_params = DockerParams(
                        **agent_run_input.agent_run_params
                    )

            async with DB() as db:
                agent_run = await db.create_agent_run(agent_run_input)
                logger.info(f"Created agent run")

            if agent_run:
                agent_run_data = agent_run.copy()
                agent_run_data.pop("_sa_instance_state", None)

            yield grpc_server_pb2.RunAgentResponse(
                status="started",
                agent_name=request.agent_name,
                consumer_id=request.consumer_id,
                agent_run_type=agent_run_input.agent_run_type,
                id=agent_run["id"],
                worker_nodes=agent_run["worker_nodes"],
            )

            # Execute the task
            if agent_run['agent_run_type'] == "package":
                logger.info(f"Running package agent: {agent_run_data}")
                task = run_agent.delay(agent_run_data)
            elif agent_run['agent_run_type'] == "docker":
                task = execute_docker_agent.delay(agent_run_data)
            else:
                yield grpc_server_pb2.RunAgentResponse(
                    status="error",
                    error_message="Invalid module type",
                    agent_name=request.agent_name,
                    consumer_id=request.consumer_id,
                    agent_run_type=agent_run['agent_run_type'],
                    id=agent_run["id"],
                    worker_nodes=agent_run["worker_nodes"],
                )
                return

            # Wait for the task to complete, sending updates periodically
            while not task.ready():
                yield grpc_server_pb2.RunAgentResponse(
                    status="running",
                    agent_name=request.agent_name,
                    consumer_id=request.consumer_id,
                    agent_run_type=agent_run['agent_run_type'],
                    id=agent_run["id"],
                    worker_nodes=agent_run["worker_nodes"],
                )
                await asyncio.sleep(5)
            
            # Retrieve the updated module run from the database
            async with DB() as db:
                updated_agent_run = await db.list_agent_runs(agent_run['id'])
                if isinstance(updated_agent_run, list):
                    updated_agent_run = updated_agent_run[0]
                updated_agent_run.pop("_sa_instance_state", None)
                logger.info(f"Updated agent run: {updated_agent_run}")

            if 'created_time' in updated_agent_run and isinstance(updated_agent_run['created_time'], datetime):
                updated_agent_run['created_time'] = updated_agent_run['created_time'].isoformat()
            if 'start_processing_time' in updated_agent_run and isinstance(updated_agent_run['start_processing_time'], datetime):
                updated_agent_run['start_processing_time'] = updated_agent_run['start_processing_time'].isoformat()
            if 'completed_time' in updated_agent_run and isinstance(updated_agent_run['completed_time'], datetime):
                updated_agent_run['completed_time'] = updated_agent_run['completed_time'].isoformat()
            logger.info(f"Yielding updated agent run: {updated_agent_run}")
            yield grpc_server_pb2.RunAgentResponse(**updated_agent_run)

        except Exception as e:
            logger.error(f"Error running agent: {e}")
            yield grpc_server_pb2.RunAgentResponse(
                status="error",
                error_message=str(e),
                agent_name=request.agent_name,
                consumer_id=request.consumer_id,
                agent_run_type=request.agent_type,
                id="",
                results=[],
                worker_nodes=[],
            )

    async def is_alive(
        self,
        request: Empty,
        context: ServicerContext,
    ) -> grpc_server_pb2.GeneralResponse:
        """Check whether the server is alive."""
        return grpc_server_pb2.GeneralResponse(ok=True)

    async def stop(
        self,
        request: Empty,
        context: ServicerContext,
    ) -> grpc_server_pb2.GeneralResponse:
        """Stop the server."""
        self.stop_event.set()
        return grpc_server_pb2.GeneralResponse(ok=True)


class GrpcServer:
    def __init__(
        self,
        host: str,
        port: int,
        node_type: str,
        node_id: str,
    ):
        self.host = host
        self.port = port
        self.node_type = node_type
        self.node_id = node_id
        self.shutdown_event = asyncio.Event()

        options = [
            ("grpc.max_send_message_length", 100 * 1024 * 1024),  # 100MB
            ("grpc.max_receive_message_length", 100 * 1024 * 1024),  # 100MB
            ("grpc.keepalive_time_ms", 60 * 1000),  # 60 seconds
            ("grpc.keepalive_timeout_ms", 60 * 1000),  # 60 seconds
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.http2.min_time_between_pings_ms", 60 * 1000),  # 60 seconds
            ("grpc.max_connection_idle_ms", 60 * 60 * 1000),  # 1 hour
            ("grpc.max_connection_age_ms", 2 * 60 * 60 * 1000),  # 2 hours
        ]

        self.server = grpc.aio.server(options=options)
        grpc_server_pb2_grpc.add_GrpcServerServicer_to_server(
            GrpcServerServicer(), self.server
        )
        self.listen_addr = f"0.0.0.0:{self.port}"
        self.server.add_insecure_port(self.listen_addr)

    async def graceful_shutdown(self, timeout: float = 30.0):
        logger.info("Starting graceful shutdown...")

        await self.server.stop(timeout)
        self.shutdown_event.set()
        logger.info("Graceful shutdown complete.")

    async def launch_server(self):
        logger.info(f"Starting server on {self.listen_addr}")
        await self.server.start()

        # Set up signal handlers for graceful shutdown
        for sig in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_running_loop().add_signal_handler(
                sig, lambda: asyncio.create_task(self.graceful_shutdown())
            )

        try:
            await self.shutdown_event.wait()
        finally:
            await self.server.wait_for_termination()
