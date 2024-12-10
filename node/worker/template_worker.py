import asyncio
import functools
import inspect
import json
import logging
import os
import pytz
import requests
import sys
import traceback
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel, create_model
from typing import List, Union

from node.client import Node
from node.config import BASE_OUTPUT_DIR, MODULES_SOURCE_DIR, NODE_TYPE, NODE_IP, NODE_PORT, NODE_ROUTING, SERVER_TYPE, LOCAL_DB_URL
from node.module_manager import install_module_with_lock, load_module, load_orchestrator_deployments
from node.schemas import AgentRun, ToolRun, EnvironmentRun, OrchestratorRun, KBRun
from node.worker.main import app
from node.worker.utils import prepare_input_dir, update_db_with_status_sync, upload_to_ipfs

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(".env")
os.environ["BASE_OUTPUT_DIR"] = f"{BASE_OUTPUT_DIR}"


if MODULES_SOURCE_DIR not in sys.path:
    sys.path.append(MODULES_SOURCE_DIR)


@app.task(bind=True, acks_late=True)
def run_agent(self, agent_run):
    try:
        agent_run = AgentRun(**agent_run)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run_module_async(agent_run))
    finally:
        # Force cleanup of channels
        app.backend.cleanup()

@app.task(bind=True, acks_late=True)
def run_tool(self, tool_run):
    try:
        tool_run = ToolRun(**tool_run)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run_module_async(tool_run))
    finally:
        # Force cleanup of channels
        app.backend.cleanup()

@app.task(bind=True, acks_late=True)
def run_orchestrator(self, orchestrator_run):
    try:
        orchestrator_run = OrchestratorRun(**orchestrator_run)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run_module_async(orchestrator_run))
    finally:
        # Force cleanup of channels
        app.backend.cleanup()

@app.task(bind=True, acks_late=True)
def run_environment(self, environment_run):
    try:
        environment_run = EnvironmentRun(**environment_run)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run_module_async(environment_run))
    finally:
        # Force cleanup of channels
        app.backend.cleanup()

@app.task(bind=True, acks_late=True)
def run_kb(self, kb_run):
    try:
        kb_run = KBRun(**kb_run)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run_module_async(kb_run))
    finally:
        # Force cleanup of channels
        app.backend.cleanup()

async def _run_module_async(module_run: Union[AgentRun, ToolRun, OrchestratorRun, EnvironmentRun, KBRun]) -> None:
    """Handles execution of agent, orchestrator, and environment runs.
    
    Args:
        module_run: Either an AgentRun, OrchestratorRun, or EnvironmentRun object
    """
    try:
        if isinstance(module_run, OrchestratorRun):
            module_run_engine = OrchestratorEngine(module_run)
        else:
            module_run_engine = ModuleRunEngine(module_run)

        module_version = f"v{module_run_engine.module['module_version']}"
        module_name = module_run_engine.module["name"]

        logger.info(f"Received {module_run_engine.module_type} run: {module_run}")
        logger.info(f"Checking if {module_run_engine.module_type} {module_name} version {module_version} is installed")

        if module_run_engine.module_type == "agent":
            module = module_run.agent_deployment.module
        elif module_run_engine.module_type == "tool":
            module = module_run.tool_deployment.module
        elif module_run_engine.module_type == "orchestrator":
            module = module_run.orchestrator_deployment.module
        elif module_run_engine.module_type == "environment":
            module = module_run.environment_deployment.module
        elif module_run_engine.module_type == "knowledge_base":
            module = module_run.kb_deployment.module

        try:
            await install_module_with_lock(module)
        except Exception as e:
            error_msg = (f"Failed to install or verify {module_run_engine.module_type} {module_name}: {str(e)}")
            logger.error(error_msg)
            logger.error(f"Traceback: {traceback.format_exc()}")
            if "Dependency conflict detected" in str(e):
                logger.error("This error is likely due to a mismatch in naptha-sdk versions. Please check and align the versions in both the agent and the main project.")
            await handle_failure(error_msg=error_msg, module_run=module_run)
            return

        await module_run_engine.init_run()
        await module_run_engine.start_run()

        if module_run_engine.module_run.status == "completed":
            await module_run_engine.complete()
        elif module_run_engine.module_run.status == "error":
            await module_run_engine.fail()

    except Exception as e:
        error_msg = f"Error in _run_module_async: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        await handle_failure(error_msg=error_msg, module_run=module_run)
        return

async def handle_failure(
    error_msg: str, 
    module_run: Union[AgentRun, OrchestratorRun, EnvironmentRun]
) -> None:
    """Handle failure for any type of module run.
    
    Args:
        error_msg: Error message to store
        module_run: Module run object (AgentRun, OrchestratorRun, or EnvironmentRun)
    """
    module_run.status = "error"
    module_run.error = True 
    module_run.error_message = error_msg
    module_run.completed_time = datetime.now(pytz.utc).isoformat()

    # Calculate duration if possible
    if hasattr(module_run, "start_processing_time") and module_run.start_processing_time:
        module_run.duration = (
            datetime.fromisoformat(module_run.completed_time)
            - datetime.fromisoformat(module_run.start_processing_time)
        ).total_seconds()
    else:
        module_run.duration = 0

    try:
        await update_db_with_status_sync(module_run=module_run)
    except Exception as db_error:
        logger.error(f"Failed to update database after error: {str(db_error)}")

async def maybe_async_call(func, *args, **kwargs):
    if inspect.iscoroutinefunction(func):
        # If it's an async function, await it directly
        return await func(*args, **kwargs)
    else:
        # If it's a sync function, run it in an executor to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, functools.partial(func, *args, **kwargs)
        )


class ModuleRunEngine:
    def __init__(self, module_run: Union[AgentRun, ToolRun, EnvironmentRun, KBRun]):
        self.module_run = module_run
        
        # Determine module type and specific attributes
        if isinstance(module_run, AgentRun):
            self.module_type = "agent"
            self.deployment = module_run.agent_deployment
        elif isinstance(module_run, ToolRun):
            self.module_type = "tool"
            self.deployment = module_run.tool_deployment
        elif isinstance(module_run, EnvironmentRun):
            self.module_type = "environment"
            self.deployment = module_run.environment_deployment
        elif isinstance(module_run, KBRun):
            self.module_type = "knowledge_base"
            self.deployment = module_run.kb_deployment
        else:
            raise ValueError(f"Invalid module run type: {type(module_run)}")

        self.module = self.deployment.module
        self.module_name = self.module["name"]
        self.module_version = f"v{self.module['module_version']}"
        self.parameters = module_run.inputs

        # Special handling for agent persona
        if self.module_type == "agent" and self.deployment.agent_config.persona_module:
            self.personas_url = self.deployment.agent_config.persona_module["module_url"]

        self.consumer = {
            "public_key": module_run.consumer_id.split(":")[1],
            "id": module_run.consumer_id,
        }

    async def init_run(self):
        logger.info(f"Initializing {self.module_type} run")
        self.module_run.status = "processing"
        self.module_run.start_processing_time = datetime.now(pytz.timezone("UTC")).isoformat()

        await update_db_with_status_sync(module_run=self.module_run)

        if "input_dir" in self.parameters or "input_ipfs_hash" in self.parameters:
            self.parameters = prepare_input_dir(
                parameters=self.parameters,
                input_dir=self.parameters.get("input_dir", None),
                input_ipfs_hash=self.parameters.get("input_ipfs_hash", None),
            )

        # Load the module
        self.module_func, self.module_run = await load_module(self.module_run, module_type=self.module_type)

    async def start_run(self):
        """Executes the module run"""
        logger.info(f"Starting {self.module_type} run")
        self.module_run.status = "running"
        await update_db_with_status_sync(module_run=self.module_run)

        logger.info(f"{self.module_type.title()} deployment: {self.deployment}")

        try:
            # Create kwargs based on module type
            if self.module_type == "agent":
                kwargs = {
                    "agent_run": self.module_run,
                    "agents_dir": MODULES_SOURCE_DIR
                }
            elif self.module_type == "tool":
                kwargs = {"tool_run": self.module_run}
            elif self.module_type == "environment":
                kwargs = {"environment_run": self.module_run}
            elif self.module_type == "knowledge_base":
                kwargs = {"kb_run": self.module_run}
            else:
                kwargs = {"module_run": self.module_run}

            response = await maybe_async_call(self.module_func, **kwargs)
        except Exception as e:
            logger.error(f"Error running {self.module_type}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        logger.info(f"{self.module_type.title()} run response: {response}")

        if isinstance(response, (dict, list, tuple)):
            response = json.dumps(response)
        elif isinstance(response, BaseModel):
            response = response.model_dump_json()

        if not isinstance(response, str):
            raise ValueError(f"{self.module_type.title()} response is not a string: {response}. Current response type: {type(response)}")

        self.module_run.results = [response]
        
        # Handle output for agent runs
        if self.module_type == "agent":
            await self.handle_output(self.deployment, response)
            
        self.module_run.status = "completed"

    async def handle_output(self, deployment, results):
        """Handles the output of the module run (only for agent and tool runs)"""
        save_location = deployment.data_generation_config.save_outputs_location
        if save_location:
            deployment.data_generation_config.save_outputs_location = save_location

        if deployment.data_generation_config.save_outputs:
            if save_location == "ipfs":
                save_path = getattr(self.deployment.data_generation_config, "save_outputs_path")
                out_msg = upload_to_ipfs(save_path)
                out_msg = f"IPFS Hash: {out_msg}"
                logger.info(f"Output uploaded to IPFS: {out_msg}")
                self.module_run.results = [out_msg]

    async def complete(self):
        """Marks the module run as completed"""
        self.module_run.status = "completed"
        self.module_run.error = False
        self.module_run.error_message = ""
        self.module_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.module_run.duration = (
            datetime.fromisoformat(self.module_run.completed_time)
            - datetime.fromisoformat(self.module_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(module_run=self.module_run)
        logger.info(f"{self.module_type.title()} run completed")

    async def fail(self):
        """Marks the module run as failed"""
        logger.error(f"Error running {self.module_type}")
        error_details = traceback.format_exc()
        logger.error(f"Traceback: {error_details}")
        self.module_run.status = "error"
        self.module_run.error = True
        self.module_run.error_message = error_details
        self.module_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.module_run.duration = (
            datetime.fromisoformat(self.module_run.completed_time)
            - datetime.fromisoformat(self.module_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(module_run=self.module_run)


class OrchestratorEngine:
    def __init__(self, orchestrator_run: OrchestratorRun):
        self.module_run = orchestrator_run
        self.deployment = orchestrator_run.orchestrator_deployment
        self.module = self.deployment.module
        self.module_type = "orchestrator"
        self.orchestrator_name = self.module["name"]
        self.orchestrator_version = f"v{self.module['module_version']}"
        self.parameters = orchestrator_run.inputs
        self.node_type = NODE_TYPE
        self.server_type = SERVER_TYPE
        if self.node_type == "direct" and self.server_type in ["http", "grpc"]:
            self.orchestrator_node = Node(f"{NODE_IP}:{NODE_PORT}", SERVER_TYPE)
            logger.info(f"Orchestrator node: {self.orchestrator_node.node_url}")
        elif self.node_type == "direct" and self.server_type == "ws":
            ip = NODE_IP
            if "http" in ip:
                ip = ip.replace("http://", "ws://")
            self.orchestrator_node = Node(f"{ip}:{NODE_PORT}", SERVER_TYPE)
            logger.info(f"Orchestrator node: {self.orchestrator_node.node_url}")
        elif self.node_type == "indirect":
            node_id = requests.get("http://localhost:7001/node_id").json()
            if not node_id:
                raise ValueError("NODE_ID environment variable is not set")
            self.orchestrator_node = Node(
                indirect_node_id=node_id, routing_url=NODE_ROUTING
            )
        else:
            raise ValueError(f"Invalid NODE_TYPE: {self.node_type}")

        self.consumer = {
            "public_key": self.module_run.consumer_id.split(":")[1],
            "id": self.module_run.consumer_id,
        }


    async def init_run(self):
        logger.info("Initializing orchestrator run")
        self.module_run.status = "processing"
        self.module_run.start_processing_time = datetime.now(pytz.timezone("UTC")).isoformat()

        await update_db_with_status_sync(module_run=self.module_run)

        if "input_dir" in self.parameters or "input_ipfs_hash" in self.parameters:
            self.parameters = prepare_input_dir(
                parameters=self.parameters,
                input_dir=self.parameters.get("input_dir", None),
                input_ipfs_hash=self.parameters.get("input_ipfs_hash", None),
            )

        
        updated_agent_deployments = await self.check_register_worker_nodes(self.module_run.orchestrator_deployment.agent_deployments)
        self.orchestrator_run.agent_deployments = updated_agent_deployments

        # Load the orchestrator
        (
            self.orchestrator_func, 
            self.module_run, 
            self.validated_data, 
        ) = await load_orchestrator_deployments(
            orchestrator_run=self.module_run,
            agent_source_dir=MODULES_SOURCE_DIR
        )
        

    async def node_url_to_node(self, node_url: str):
        """
        Converts the node url to a node object
        """
        if node_url.startswith('ws://'):
            return Node(node_url=node_url, server_type='ws'), node_url
        elif node_url.startswith('http://'):
            return Node(node_url=node_url, server_type='http'), node_url
        elif node_url.startswith('grpc://'):
            _node_url = node_url.replace('grpc://', '')
            return Node(node_url=_node_url, server_type='grpc'), node_url
        else:
            if node_url.endswith('/'):
                node_url = node_url[:-1]
            if "://" in node_url:
                node_url = node_url.split("://")[1]

            temp_url = f"http://{node_url}"
            temp_node = Node(node_url=temp_url, server_type='http')
            health = await temp_node.check_health()
            if health:
                ws_url = f"ws://{node_url}"
                return Node(node_url=ws_url, server_type='ws'), ws_url
            else:
                return Node(node_url=node_url, server_type='grpc'), f"grpc://{node_url}"
        
    async def check_register_worker_nodes(self, agent_deployments: List):
        """
        Validates and registers user access rights for worker nodes.
        Skips validation for worker nodes on the same domain as the orchestrator.
        """
        logger.info(f"Validating user {self.consumer} access for {len(agent_deployments)} worker nodes")

        def extract_domain(url: str) -> str:
            """Extract clean domain from URL, removing protocol and port"""
            domain = url.split("://")[-1].split(":")[0]
            return domain

        async def process_worker_node(worker_node, node_url: str):
            """Handle user validation and registration for a single worker node"""
            async with worker_node as node:
                consumer = await node.check_user(user_input=self.consumer)
                
                if consumer["is_registered"]:
                    logger.info(f"User validated on worker node: {node_url}")
                    return
                
                logger.info(f"Registering new user on worker node: {node_url}")
                consumer = await node.register_user(user_input=consumer)
                logger.info(f"User registration complete on worker node: {node_url}")

        for deployment in agent_deployments:
            worker_url = deployment.worker_node_url
            if not worker_url:
                continue

            try:
                # Check if worker node is on same domain as orchestrator
                worker_domain = extract_domain(worker_url)
                orchestrator_domain = extract_domain(self.orchestrator_node.node_url)

                # Process the worker node
                worker_node, worker_node_url = await self.node_url_to_node(worker_url)
                deployment.worker_node_url = worker_node_url

                if worker_domain == orchestrator_domain:
                    logger.info(f"Skipping validation for same-domain worker node: {worker_url}")
                    continue
                await process_worker_node(worker_node, worker_url)

            except Exception as e:
                logger.error(f"Error processing worker node {worker_url}: {e}")
                raise

        return agent_deployments

    async def start_run(self):
        logger.info("Starting orchestrator run")
        self.module_run.status = "running"
        await update_db_with_status_sync(module_run=self.module_run)

        try:
            response = await maybe_async_call(
                self.orchestrator_func,
                orchestrator_run=self.module_run,
                db_url=LOCAL_DB_URL,
                agents_dir=MODULES_SOURCE_DIR,
            )
        except Exception as e:
            logger.error(f"Error running orchestrator: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        logger.info(f"Orchestrator run response: {response}")

        if isinstance(response, (dict, list, tuple)):
            response = json.dumps(response)
        elif isinstance(response, BaseModel):
            response = response.model_dump_json()

        if not isinstance(response, str):
            raise ValueError(f"Agent/orchestrator response is not a string: {response}. Current response type: {type(response)}")

        self.module_run.results = [response]
        self.module_run.status = "completed"

    async def complete(self):
        self.module_run.status = "completed"
        self.module_run.error = False
        self.module_run.error_message = ""
        self.module_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.module_run.duration = (
            datetime.fromisoformat(self.module_run.completed_time)
            - datetime.fromisoformat(self.module_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(module_run=self.module_run)
        logger.info("Orchestrator run completed")

    async def fail(self):
        logger.error("Error running flow")
        error_details = traceback.format_exc()
        logger.error(f"Traceback: {error_details}")
        self.module_run.status = "error"
        self.module_run.error = True
        self.module_run.error_message = error_details
        self.module_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.module_run.duration = (
            datetime.fromisoformat(self.module_run.completed_time)
            - datetime.fromisoformat(self.module_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(orchestrator_run=self.module_run)
