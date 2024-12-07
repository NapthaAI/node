import os
import asyncio
import grpc
import json
import signal
import logging
import traceback
from datetime import datetime
from google.protobuf.empty_pb2 import Empty
from google.protobuf.json_format import MessageToDict
from grpc import ServicerContext
from google.protobuf import struct_pb2
from node.storage.db.db import DB
from node.storage.hub.hub import Hub
from node.user import register_user, check_user
from node.worker.docker_worker import execute_docker_agent
from node.worker.template_worker import run_agent, run_orchestrator
from node.server import grpc_server_pb2, grpc_server_pb2_grpc
from node.schemas import OrchestratorRunInput

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

    async def RunAgent(self, request, context):
        try:
            logger.info(f"Running agent input: {request}")
            
            async with Hub() as hub:
                _, _, _ = await hub.signin(
                    os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                )
                agent_module = await hub.list_agents(f"{request.agent_deployment.module.name}")
                logger.info(f"Found Agent: {agent_module}")

            if not agent_module:
                yield grpc_server_pb2.AgentRun(
                    status="error",
                    error=True,
                    error_message="Agent not found",
                    consumer_id=request.consumer_id,
                    id="",
                    results=[],
                )
                return

            # Convert agent_module to dict if it's not already
            if isinstance(agent_module, dict):
                module_dict = agent_module
            else:  # Assuming it's an AgentModule instance
                module_dict = {
                    'id': agent_module.id,
                    'name': agent_module.name,
                    'description': agent_module.description,
                    'author': agent_module.author,
                    'url': agent_module.url,
                    'type': agent_module.type.value if hasattr(agent_module.type, 'value') else agent_module.type,
                    'version': agent_module.version,
                    'entrypoint': agent_module.entrypoint,
                    'personas_urls': agent_module.personas_urls
                }

            # Convert to dictionary format for database
            agent_run_input = {
                'consumer_id': request.consumer_id,
                'inputs': MessageToDict(request.input_struct) if request.HasField('input_struct') else {}, 
                'agent_deployment': {
                    'name': request.agent_deployment.name,  
                    'module': module_dict,
                    'worker_node_url': request.agent_deployment.worker_node_url,
                }
            }

            async with DB() as db:
                agent_run = await db.create_agent_run(agent_run_input)
                logger.info(f"Created agent run")

            # Initial response
            yield grpc_server_pb2.AgentRun(
                status="started",
                error=False,
                id=agent_run.id,
                consumer_id=agent_run.consumer_id,
            )

            if not isinstance(agent_run, dict):
                agent_run = agent_run.__dict__
                agent_run.pop("_sa_instance_state", None)

            if not isinstance(agent_run['agent_deployment'], dict):
                agent_run['agent_deployment'] = agent_run['agent_deployment'].model_dump()

            logger.info(f"Agent run: {agent_run}")

            # Execute the task
            module_type = module_dict['type']
            if module_type == "package":
                task = run_agent.delay(agent_run)
            elif module_type == "docker":
                task = execute_docker_agent.delay(agent_run)
            else:
                yield grpc_server_pb2.AgentRun(
                    status="error",
                    error=True,
                    error_message="Invalid module type",
                    id=agent_run['id'],
                    consumer_id=agent_run['consumer_id'],
                    results=[],
                )
                return

            # Wait for the task to complete, sending updates periodically
            while not task.ready():
                yield grpc_server_pb2.AgentRun(
                    status="running",
                    error=False,
                    id=agent_run['id'],
                    consumer_id=agent_run['consumer_id'],
                    results=[],
                )
                await asyncio.sleep(5)
                
            # Retrieve the updated run from the database
            async with DB() as db:
                updated_run = await db.list_agent_runs(agent_run['id'])
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
                inputs=inputs,
                agent_deployment=agent_deployment,
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
                consumer_id=request.consumer_id if request else "",
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

    async def RunOrchestrator(self, request, context):
        try:
            logger.info(f"Running orchestrator input: {request}")
            
            async with Hub() as hub:
                _, _, _ = await hub.signin(
                    os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                )
                # Get just the module name
                module_name = request.orchestrator_deployment.name
                logger.info(f"Looking for orchestrator: {module_name}")
                
                orchestrator_module = await hub.list_orchestrators(module_name)
                logger.info(f"Found Orchestrator: {orchestrator_module}")

                if not orchestrator_module:
                    yield grpc_server_pb2.OrchestratorRun(
                        status="error",
                        error=True,
                        error_message=f"Orchestrator not found: {module_name}",
                        consumer_id=request.consumer_id,
                    )
                    return

                # Convert orchestrator_module to proper format if needed
                if not isinstance(orchestrator_module, dict):
                    orchestrator_module = {
                        'id': orchestrator_module.id,
                        'name': orchestrator_module.name,
                        'description': orchestrator_module.description,
                        'author': orchestrator_module.author,
                        'url': orchestrator_module.url,
                        'type': orchestrator_module.type.value if hasattr(orchestrator_module.type, 'value') else orchestrator_module.type,
                        'version': orchestrator_module.version,
                        'entrypoint': orchestrator_module.entrypoint,
                    }

            # Create run input dictionary
            orchestrator_run_input = {
                'consumer_id': request.consumer_id,
                'inputs': MessageToDict(
                    request.input_struct, 
                    preserving_proto_field_name=True) if request.HasField('input_struct') else {},
                'orchestrator_deployment': {
                    'name': request.orchestrator_deployment.name,
                    'module': orchestrator_module,
                    'orchestrator_node_url': request.orchestrator_deployment.orchestrator_node_url,
                },
                'agent_deployments': [
                    MessageToDict(
                        dep, 
                        preserving_proto_field_name=True) for dep in request.agent_deployments
                ],
                'environment_deployments': [
                    MessageToDict(
                        dep,
                        preserving_proto_field_name=True) for dep in request.environment_deployments
                ]
            }

            logger.info(f"Orchestrator run input: {orchestrator_run_input}")

            async with DB() as db:
                orchestrator_run = await db.create_orchestrator_run(orchestrator_run_input)
                logger.info(f"Created orchestrator run: {orchestrator_run}")

            if not isinstance(orchestrator_run, dict):
                orchestrator_run = orchestrator_run.model_dump()

            # Initial response
            yield grpc_server_pb2.OrchestratorRun(
                status="started",
                error=False,
                id=orchestrator_run['id'],
                consumer_id=orchestrator_run['consumer_id'],
            )

            # Convert to dictionary if needed
            if not isinstance(orchestrator_run, dict):
                orchestrator_run = orchestrator_run.__dict__
                orchestrator_run.pop("_sa_instance_state", None)

            # Execute the task
            module_type = orchestrator_module['type']
            if module_type == "package":
                task = run_orchestrator.delay(orchestrator_run)
            else:
                yield grpc_server_pb2.OrchestratorRun(
                    status="error",
                    error=True,
                    error_message=f"Invalid module type: {module_type}",
                    id=orchestrator_run['id'],
                    consumer_id=orchestrator_run['consumer_id'],
                )
                return

            # Wait for the task to complete, sending updates periodically
            while not task.ready():
                yield grpc_server_pb2.OrchestratorRun(
                    status="running",
                    error=False,
                    id=orchestrator_run['id'],
                    consumer_id=orchestrator_run['consumer_id'],
                )
                await asyncio.sleep(5)
            
            # Retrieve the updated run from the database
            async with DB() as db:
                updated_run = await db.list_orchestrator_runs(orchestrator_run['id'])
                if isinstance(updated_run, list):
                    updated_run = updated_run[0]
                if not isinstance(updated_run, dict):
                    updated_run = updated_run.__dict__
                updated_run.pop("_sa_instance_state", None)

            # Convert timestamps to strings if they exist
            for time_field in ['created_time', 'start_processing_time', 'completed_time']:
                if time_field in updated_run and isinstance(updated_run[time_field], datetime):
                    updated_run[time_field] = updated_run[time_field].isoformat()

            logger.info(f"Updated orchestrator run: {updated_run}")

            # Create inputs struct
            inputs = struct_pb2.Struct()
            if updated_run.get('inputs'):
                inputs.update(updated_run['inputs'])

            # Final response
            final_response = grpc_server_pb2.OrchestratorRun(
                consumer_id=updated_run.get('consumer_id', ''),
                status=updated_run.get('status', 'completed'),
                error=updated_run.get('error', False),
                id=updated_run.get('id', ''),
                results=updated_run.get('results', []),
                error_message=updated_run.get('error_message', ''),
                created_time=updated_run.get('created_time', ''),
                start_processing_time=updated_run.get('start_processing_time', ''),
                completed_time=updated_run.get('completed_time', ''),
                duration=float(updated_run.get('duration', 0.0)),
                agent_runs=updated_run.get('agent_runs', []),
                input_schema_ipfs_hash=updated_run.get('input_schema_ipfs_hash', '')
            )
            final_response.input_struct.CopyFrom(inputs)

            logger.info(f"Sending final response: {final_response}")
            yield final_response
            logger.info("Final response sent")

        except Exception as e:
            logger.error(f"Error running orchestrator: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            yield grpc_server_pb2.OrchestratorRun(
                status="error",
                error=True,
                error_message=str(e),
                consumer_id=request.consumer_id if request else "",
            )

    async def CheckOrchestratorRun(self, request, context):
        try:
            logger.info(f"Checking orchestrator run: {request.id}")
            
            async with DB() as db:
                orchestrator_run = await db.list_orchestrator_runs(request.id)
                if isinstance(orchestrator_run, list):
                    orchestrator_run = orchestrator_run[0]
                orchestrator_run.pop("_sa_instance_state", None)

            if not orchestrator_run:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details('Orchestrator run not found')
                return grpc_server_pb2.OrchestratorRun()

            return grpc_server_pb2.OrchestratorRun(**orchestrator_run)

        except Exception as e:
            logger.error(f"Error checking orchestrator run: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return grpc_server_pb2.OrchestratorRun()

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