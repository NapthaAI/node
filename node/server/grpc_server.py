import os
import asyncio
import grpc
import json
import signal
import logging
import traceback
from datetime import datetime
from pathlib import Path
from google.protobuf.empty_pb2 import Empty
from google.protobuf.json_format import MessageToDict
from grpc import ServicerContext
from typing import Dict, Any
from google.protobuf import struct_pb2
from node.storage.db.db import DB
from node.storage.hub.hub import Hub
from node.user import register_user, check_user
from node.worker.docker_worker import execute_docker_agent
from node.worker.template_worker import run_agent, run_orchestrator
from node.server import grpc_server_pb2, grpc_server_pb2_grpc
from node.schemas import AgentDeployment, AgentRunInput
from node.module_manager import setup_module_deployment
from node.config import MODULES_SOURCE_DIR

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
        
        success, user_data = await register_user(input_data)
        
        if success:
            logger.info(f"User registration result: {user_data}")
            return grpc_server_pb2.RegisterUserResponse(**user_data)
        else:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details('User registration failed')
            return grpc_server_pb2.RegisterUserResponse()
    
    async def create_module(self, module_deployment: AgentDeployment) -> Dict[str, Any]:
        """
        Unified method to create and install any type of module and its sub-modules
        """
        try:
            # Determine module type and configuration
            if isinstance(module_deployment, AgentDeployment):
                module_type = "agent"
                module_name = module_deployment.module["name"] if isinstance(module_deployment.module, dict) else module_deployment.module.name
            else:
                raise HTTPException(status_code=400, detail="Invalid module deployment type")

            logger.info(f"Creating {module_type}: {module_deployment}")

            main_module_name = module_deployment.module['name']
            main_module_path = Path(f"{MODULES_SOURCE_DIR}/{main_module_name}/{main_module_name}")

            module_deployment = await setup_module_deployment(module_type, main_module_path / "configs/deployment.json", module_deployment.name, module_deployment)

            return module_deployment

        except Exception as e:
            logger.error(f"Failed to create module: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise Exception(f"Failed to create module: {str(e)}")
    
    async def RunAgent(self, request, context):
        try:
            logger.info(f"Running task: {request}")
            
            # convert proto to dict to AgentRunInput
            request = MessageToDict(request)

            if 'consumerId' in request:
                request['consumer_id'] = request['consumerId']
                del request['consumerId']

            logger.info(f"Request: {request}")
            logger.info(f"Request type: {type(request)}")

            # convert dict to AgentRunInput
            agent_run_input = AgentRunInput(**request)
            agent_run_input.inputs = request['inputStruct']

            if not agent_run_input.deployment.initialized == True:
                agent_deployment = await self.create_module(agent_run_input.deployment)
                agent_run_input.deployment = agent_deployment           

            async with DB() as db:
                agent_run = await db.create_agent_run(agent_run_input)
                logger.info(f"Created agent run")
                agent_run_data = agent_run.model_dump()

            # Initial response
            yield grpc_server_pb2.AgentRun(
                status="started",
                error=False,
                id=agent_run_data['id'],
                consumer_id=agent_run_data['consumer_id'],
            )

            # execute the task
            if isinstance(agent_run_input.deployment.module, dict):
                module_type = agent_run_input.deployment.module['module_type']
            else:
                module_type = agent_run_input.deployment.module.module_type

            if module_type == "package":
                task = run_agent.delay(agent_run_data)
            elif module_type == "docker":
                task = execute_docker_agent.delay(agent_run_data)
            else:
                yield grpc_server_pb2.AgentRun(
                    status="error",
                    error=True,
                    error_message="Invalid agent run type",
                    id=agent_run_data['id'],
                    consumer_id=agent_run_data['consumer_id'],
                    results=[],
                )
                return
            
            # Wait for the task to complete, sending updates periodically
            while not task.ready():
                yield grpc_server_pb2.AgentRun(
                    status="running",
                    error=False,
                    id=agent_run_data['id'],
                    consumer_id=agent_run_data['consumer_id'],
                    results=[],
                )
                await asyncio.sleep(5)
                
            # Retrieve the updated run from the database
            async with DB() as db:
                updated_run = await db.list_agent_runs(agent_run_data['id'])
                if isinstance(updated_run, list):
                    updated_run = updated_run[0]
                    
            if isinstance(updated_run, dict):
                updated_run.pop("_sa_instance_state", None)
            else:
                updated_run = updated_run.__dict__
                updated_run.pop("_sa_instance_state", None)

            # Convert timestamps to strings if they exist
            if 'created_time' in updated_run and isinstance(updated_run['created_time'], datetime):
                updated_run['created_time'] = updated_run['created_time'].isoformat()
            if 'start_processing_time' in updated_run and isinstance(updated_run['start_processing_time'], datetime):
                updated_run['start_processing_time'] = updated_run['start_processing_time'].isoformat()
            if 'completed_time' in updated_run and isinstance(updated_run['completed_time'], datetime):
                updated_run['completed_time'] = updated_run['completed_time'].isoformat()

            logger.info(f"Updated agent run: {updated_run}")

            # Create the final response
            inputs = struct_pb2.Struct()
            inputs.update(updated_run.get('inputs', {}))

            agent_deployment = struct_pb2.Struct()
            agent_deployment.update(updated_run.get('agent_deployment', {}))

            final_response = grpc_server_pb2.AgentRun(
                consumer_id=updated_run.get("consumer_id", ""),
                input_struct=inputs,  # Changed from 'inputs' to 'input_struct'
                deployment=updated_run.get("deployment", {}),
                status=updated_run.get("status", "completed"),
                error=False,
                id=updated_run.get("id", ""),
                results=updated_run.get("results", []),
                error_message=updated_run.get("error_message", ""),
                created_time=updated_run.get("created_time", ""),
                start_processing_time=updated_run.get("start_processing_time", ""),
                completed_time=updated_run.get("completed_time", ""),
                duration=float(updated_run.get("duration", 0.0)),
                input_schema_ipfs_hash=updated_run.get("input_schema_ipfs_hash", ""),
            )

            # logger.info(f"Sending final response: {final_response}")
            yield final_response
            logger.info(f"Sent final response")

        except Exception as e:
            logger.error(f"Error running agent: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            yield grpc_server_pb2.AgentRun(
                status="error",
                error=True,
                error_message=str(e),
                consumer_id=request.get('consumer_id', ''),  # Fixed: use dict get method
                id="",
                results=[],
            )

    async def CheckAgentRun(self, request, context):
        try:
            logger.info(f"Checking agent run: {request.id}")
            
            async with DB() as db:  
                agent_run = await db.list_agent_runs(request.id)
                if isinstance(agent_run, list):
                    agent_run = agent_run[0]
                agent_run.pop("_sa_instance_state", None)

            if not agent_run:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details('Agent run not found')
                return grpc_server_pb2.AgentRun()

            return grpc_server_pb2.AgentRun(**agent_run)

        except Exception as e:
            logger.error(f"Error checking agent run: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return grpc_server_pb2.AgentRun()

    async def is_alive(self, request: Empty, context: ServicerContext) -> grpc_server_pb2.GeneralResponse:
        """Check whether the server is alive."""
        return grpc_server_pb2.GeneralResponse(ok=True)

    async def stop(self, request: Empty, context: ServicerContext) -> grpc_server_pb2.GeneralResponse:
        """Stop the server."""
        self.stop_event.set()
        return grpc_server_pb2.GeneralResponse(ok=True)

class GrpcServer:
    def __init__(
        self,
        host: str,
        port: int,
        node_id: str,
    ):
        self.host = host
        self.port = port
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

    async def graceful_shutdown(self, timeout: float = 3.0):
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



if __name__ == "__main__":
    # Create and configure logging first
    logging.basicConfig(level=logging.INFO)
    
    # Create a new event loop explicitly
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        server = GrpcServer(
            host="0.0.0.0",
            port=7002,
            node_type="worker",
            node_id="1234567890"
        )
        loop.run_until_complete(server.launch_server())
    finally:
        loop.close()