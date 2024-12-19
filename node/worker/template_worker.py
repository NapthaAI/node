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
from node.module_manager import ensure_module_installation_with_lock, load_module, load_orchestrator
from node.schemas import AgentRun, EnvironmentRun, OrchestratorRun, KBRun
from node.worker.main import app
from node.worker.task_engine import TaskEngine
from node.worker.utils import prepare_input_dir, update_db_with_status_sync, upload_to_ipfs, upload_json_string_to_ipfs

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

async def _run_module_async(module_run: Union[AgentRun, OrchestratorRun, EnvironmentRun, KBRun]) -> None:
    """Handles execution of agent, orchestrator, and environment runs.
    
    Args:
        module_run: Either an AgentRun, OrchestratorRun, or EnvironmentRun object
    """
    try:
        # Determine module type
        if isinstance(module_run, AgentRun):
            module_type = "agent"
            module_deployment = module_run.agent_deployment
            engine_class = AgentEngine
        elif isinstance(module_run, OrchestratorRun):
            module_type = "orchestrator"
            module_deployment = module_run.orchestrator_deployment
            engine_class = OrchestratorEngine
        elif isinstance(module_run, EnvironmentRun):
            module_type = "environment"
            module_deployment = module_run.environment_deployment
            engine_class = EnvironmentEngine
        elif isinstance(module_run, KBRun):
            logger.info(f"Received KB run: {module_run}")
            module_type = "knowledge_base"
            module_deployment = module_run.kb_deployment
            engine_class = KBEngine
        else:
            raise ValueError(f"Invalid module type: {type(module_run)}")
        
        module_version = f"v{module_deployment.module['module_version']}"
        module_name = module_deployment.module["name"]

        logger.info(f"Received {module_type} run: {module_run}")
        logger.info(f"Checking if {module_type} {module_name} version {module_version} is installed")

        try:
            await ensure_module_installation_with_lock(module_run, module_version)
        except Exception as e:
            error_msg = (f"Failed to install or verify {module_type} {module_name}: {str(e)}")
            logger.error(error_msg)
            logger.error(f"Traceback: {traceback.format_exc()}")
            if "Dependency conflict detected" in str(e):
                logger.error("This error is likely due to a mismatch in naptha-sdk versions. Please check and align the versions in both the agent and the main project.")
            await handle_failure(error_msg=error_msg, module_run=module_run)
            return

        logger.info(f"{module_type.title()} {module_name} version {module_version} is installed and verified.")

        logger.info(f"Starting {module_type} run")
        workflow_engine = engine_class(module_run)
        await workflow_engine.init_run()
        await workflow_engine.start_run()

        # Get the status attribute based on module type
        status = getattr(workflow_engine, f"{module_type}_run").status

        if status == "completed":
            await workflow_engine.complete()
        elif status == "error":
            await workflow_engine.fail()

    except Exception as e:
        error_msg = f"Error in _run_{module_type}_async: {str(e)}"
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


class AgentEngine:
    def __init__(self, agent_run: AgentRun):
        self.agent_run = agent_run
        self.module = agent_run.agent_deployment.module
        self.agent_name = self.module["name"]
        self.agent_version = f"v{self.module['module_version']}"
        self.parameters = agent_run.inputs

        if self.agent_run.agent_deployment.agent_config.persona_module:
            self.personas_url = self.agent_run.agent_deployment.agent_config.persona_module["module_url"]

        self.consumer = {
            "public_key": agent_run.consumer_id.split(":")[1],
            "id": agent_run.consumer_id,
        }

    async def init_run(self):
        logger.info("Initializing agent run")
        self.agent_run.status = "processing"
        self.agent_run.start_processing_time = datetime.now(pytz.timezone("UTC")).isoformat()

        await update_db_with_status_sync(module_run=self.agent_run)

        if "input_dir" in self.parameters or "input_ipfs_hash" in self.parameters:
            self.parameters = prepare_input_dir(
                parameters=self.parameters,
                input_dir=self.parameters.get("input_dir", None),
                input_ipfs_hash=self.parameters.get("input_ipfs_hash", None),
            )

        # Load the agent
        self.agent_func, self.agent_run = await load_module(self.agent_run, module_type="agent")

    async def start_run(self):
        """Executes the agent run"""
        logger.info("Starting agent run")
        self.agent_run.status = "running"
        await update_db_with_status_sync(module_run=self.agent_run)

        logger.info(f"Agent deployment: {self.agent_run.agent_deployment}")

        try:
            response = await maybe_async_call(
                self.agent_func,
                agent_run=self.agent_run,
                agents_dir=MODULES_SOURCE_DIR,
            )
        except Exception as e:
            logger.error(f"Error running agent: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        logger.info(f"Agent run response: {response}")

        if isinstance(response, (dict, list, tuple)):
            response = json.dumps(response)
        elif isinstance(response, BaseModel):
            response = response.model_dump_json()

        if not isinstance(response, str):
            raise ValueError(f"Agent response is not a string: {response}. Current response type: {type(response)}")

        self.agent_run.results = [response]
        await self.handle_output(self.agent_run.agent_deployment, response)
        self.agent_run.status = "completed"

    async def handle_output(self, agent_deployment, results):
        """Handles the output of the agent run"""
        save_location = agent_deployment.data_generation_config.save_outputs_location
        if save_location:
            agent_deployment.data_generation_config.save_outputs_location = save_location

        if agent_deployment.data_generation_config.save_outputs:
            if save_location == "ipfs":
                out_msg = upload_to_ipfs(self.agent_run.agent_deployment.data_generation_config.save_outputs_path)
                out_msg = f"IPFS Hash: {out_msg}"
                logger.info(f"Output uploaded to IPFS: {out_msg}")
                self.agent_run.results = [out_msg]

    async def complete(self):
        """Marks the agent run as completed"""
        self.agent_run.status = "completed"
        self.agent_run.error = False
        self.agent_run.error_message = ""
        self.agent_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.agent_run.duration = (
            datetime.fromisoformat(self.agent_run.completed_time)
            - datetime.fromisoformat(self.agent_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(module_run=self.agent_run)
        logger.info("Agent run completed")

    async def fail(self):
        """Marks the agent run as failed"""
        logger.error("Error running agent")
        error_details = traceback.format_exc()
        logger.error(f"Traceback: {error_details}")
        self.agent_run.status = "error"
        self.agent_run.error = True
        self.agent_run.error_message = error_details
        self.agent_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.agent_run.duration = (
            datetime.fromisoformat(self.agent_run.completed_time)
            - datetime.fromisoformat(self.agent_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(module_run=self.agent_run)


class EnvironmentEngine:
    def __init__(self, environment_run: EnvironmentRun):
        self.environment_run = environment_run
        self.module = environment_run.environment_deployment.module
        self.environment_name = self.module["name"]
        self.environment_version = f"v{self.module['module_version']}"
        self.parameters = environment_run.inputs

        self.consumer = {
            "public_key": environment_run.consumer_id.split(":")[1],
            "id": environment_run.consumer_id,
        }

    async def init_run(self):
        logger.info("Initializing environment run")
        self.environment_run.status = "processing"
        self.environment_run.start_processing_time = datetime.now(pytz.timezone("UTC")).isoformat()

        await update_db_with_status_sync(module_run=self.environment_run)

        if "input_dir" in self.parameters or "input_ipfs_hash" in self.parameters:
            self.parameters = prepare_input_dir(
                parameters=self.parameters,
                input_dir=self.parameters.get("input_dir", None),
                input_ipfs_hash=self.parameters.get("input_ipfs_hash", None),
            )

        self.environment_func, self.environment_run = await load_module(self.environment_run, module_type="environment")

    async def start_run(self):
        """Executes the environment run"""
        logger.info("Starting environment run")
        self.environment_run.status = "running"
        await update_db_with_status_sync(module_run=self.environment_run)

        logger.info(f"Environment deployment: {self.environment_run.environment_deployment}")

        try:
            response = await maybe_async_call(
                self.environment_func,
                environment_run=self.environment_run,
            )
        except Exception as e:
            logger.error(f"Error running environment: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        logger.info(f"Environment run response: {response}")

        if isinstance(response, (dict, list, tuple)):
            response = json.dumps(response)
        elif isinstance(response, BaseModel):
            response = response.model_dump_json()

        if not isinstance(response, str):
            raise ValueError(f"Environment response is not a string: {response}. Current response type: {type(response)}")

        self.environment_run.results = [response]
        self.environment_run.status = "completed"

    async def complete(self):
        """Marks the environment run as completed"""
        self.environment_run.status = "completed"
        self.environment_run.error = False
        self.environment_run.error_message = ""
        self.environment_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.environment_run.duration = (
            datetime.fromisoformat(self.environment_run.completed_time)
            - datetime.fromisoformat(self.environment_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(module_run=self.environment_run)
        logger.info("Environment run completed")

    async def fail(self):
        """Marks the environment run as failed"""
        logger.error("Error running environment")
        error_details = traceback.format_exc()
        logger.error(f"Traceback: {error_details}")
        self.environment_run.status = "error"
        self.environment_run.error = True
        self.environment_run.error_message = error_details
        self.environment_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.environment_run.duration = (
            datetime.fromisoformat(self.environment_run.completed_time)
            - datetime.fromisoformat(self.environment_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(module_run=self.environment_run)


class KBEngine:
    def __init__(self, kb_run: KBRun):
        self.knowledge_base_run = kb_run
        self.module = kb_run.kb_deployment.module
        self.kb_name = self.module["name"]
        self.kb_version = f"v{self.module['module_version']}"
        self.parameters = kb_run.inputs

        self.consumer = {
            "public_key": kb_run.consumer_id.split(":")[1],
            "id": kb_run.consumer_id,
        }

    async def init_run(self):
        logger.info("Initializing knowledge base run")
        self.knowledge_base_run.status = "processing"
        self.knowledge_base_run.start_processing_time = datetime.now(pytz.timezone("UTC")).isoformat()

        await update_db_with_status_sync(module_run=self.knowledge_base_run)

        self.kb_func, self.knowledge_base_run = await load_module(self.knowledge_base_run, module_type="knowledge_base")

    async def start_run(self):
        """Executes the knowledge base run"""
        logger.info("Starting knowledge base run")
        self.knowledge_base_run.status = "running"
        await update_db_with_status_sync(module_run=self.knowledge_base_run)

        try:
            response = await maybe_async_call(
                self.kb_func,
                kb_run=self.knowledge_base_run,
            )
        except Exception as e:
            logger.error(f"Error running knowledge base: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        logger.info(f"Knowledge base run response: {response}")

        if isinstance(response, (dict, list, tuple)):
            response = json.dumps(response)
        elif isinstance(response, BaseModel):
            response = response.model_dump_json()

        self.knowledge_base_run.results = [response]
        self.knowledge_base_run.status = "completed"

    async def complete(self):
        """Marks the knowledge base run as completed"""
        self.knowledge_base_run.status = "completed"
        self.knowledge_base_run.error = False
        self.knowledge_base_run.error_message = ""
        self.knowledge_base_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.knowledge_base_run.duration = (
            datetime.fromisoformat(self.knowledge_base_run.completed_time)
            - datetime.fromisoformat(self.knowledge_base_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(module_run=self.knowledge_base_run)
        logger.info("Knowledge base run completed")

    async def fail(self):
        """Marks the knowledge base run as failed"""
        logger.error("Error running knowledge base")
        error_details = traceback.format_exc()
        logger.error(f"Traceback: {error_details}")
        self.knowledge_base_run.status = "error"
        self.knowledge_base_run.error = True
        self.knowledge_base_run.error_message = error_details
        self.knowledge_base_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.knowledge_base_run.duration = (
            datetime.fromisoformat(self.knowledge_base_run.completed_time)
            - datetime.fromisoformat(self.knowledge_base_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(module_run=self.knowledge_base_run)
        logger.info("Knowledge base run completed")


class OrchestratorEngine:
    def __init__(self, orchestrator_run: OrchestratorRun):
        self.orchestrator_run = orchestrator_run
        self.orchestrator_name = orchestrator_run.orchestrator_deployment.module["name"]
        self.orchestrator_version = f"v{orchestrator_run.orchestrator_deployment.module['module_version']}"
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
            "public_key": self.orchestrator_run.consumer_id.split(":")[1],
            "id": self.orchestrator_run.consumer_id,
        }


    async def init_run(self):
        logger.info("Initializing orchestrator run")
        self.orchestrator_run.status = "processing"
        self.orchestrator_run.start_processing_time = datetime.now(pytz.timezone("UTC")).isoformat()

        await update_db_with_status_sync(module_run=self.orchestrator_run)

        if "input_dir" in self.parameters or "input_ipfs_hash" in self.parameters:
            self.parameters = prepare_input_dir(
                parameters=self.parameters,
                input_dir=self.parameters.get("input_dir", None),
                input_ipfs_hash=self.parameters.get("input_ipfs_hash", None),
            )

        # convert inputs to BaseModel if dict
        if isinstance(self.parameters, dict):
            # Create a dynamic model with types based on the values
            DynamicParams = create_model(
                'DynamicParams',
                **{k: (type(v), v) for k, v in self.parameters.items()}
            )
            parameters = DynamicParams(**self.parameters)
            self.orchestrator_run.inputs = parameters

        # TODO: in the new version of the node, is this still needed?
        await self.check_register_worker_nodes(self.orchestrator_run.orchestrator_deployment.agent_deployments)

        # Load the orchestrator
        (
            self.orchestrator_func, 
            self.orchestrator_run, 
            self.validated_data, 
        ) = await load_orchestrator(
            orchestrator_run=self.orchestrator_run,
            agent_source_dir=MODULES_SOURCE_DIR
        )
        

    def node_url_to_node(self, node_url: str):
        """
        Converts the node url to a node object
        """
        if 'ws://' in node_url:
            return Node(node_url=node_url, server_type='ws')
        elif 'http://' in node_url:
            return Node(node_url=node_url, server_type='http')
        elif 'grpc://' in node_url:
            node_url = node_url.replace('grpc://', '')
            return Node(node_url=node_url, server_type='grpc')
        else:
            raise ValueError(f"Invalid node URL: {node_url}")
        
    async def check_register_worker_nodes(self, agent_deployments: List):
        """
        Checks if the user has the right to use the worker nodes
        """
        logger.info(f"Checking user: {self.consumer} on worker nodes: {agent_deployments}")
        for agent_deployment in agent_deployments:
            logger.info(f"Agent deployment: {agent_deployment}")
            worker_node_url = agent_deployment.worker_node_url
            logger.info(f"Checking user: {self.consumer} on worker node: {worker_node_url}")
            if worker_node_url:
                worker_node = self.node_url_to_node(worker_node_url)
                logger.info(f"Checking user: {self.consumer} on worker node: {worker_node_url}")

                # get only the domain from the node url
                if "://" in worker_node_url:
                    worker_node_url_domain = worker_node_url.split("://")[1]        
                else:
                    worker_node_url_domain = worker_node_url

                if ":" in worker_node_url_domain:
                    worker_node_url_domain = worker_node_url_domain.split(":")[0]

                # get only the domain from the orchestrator node url
                if "://" in self.orchestrator_node.node_url:
                    orchestrator_node_url_domain = self.orchestrator_node.node_url.split("://")[1]
                else:
                    orchestrator_node_url_domain = self.orchestrator_node.node_url
            
                if ":" in orchestrator_node_url_domain:
                    orchestrator_node_url_domain = orchestrator_node_url_domain.split(":")[0]

                if worker_node_url_domain == orchestrator_node_url_domain:
                    logger.info(f"Skipping check user on orchestrator node: {worker_node_url}")
                    continue

                async with worker_node as node:
                    consumer = await node.check_user(user_input=self.consumer)
                if consumer["is_registered"] is True:
                    logger.info(f"Found user: {consumer} on worker node: {worker_node_url}")
                elif consumer["is_registered"] is False:
                    logger.info(f"No user found. Registering user: {consumer} on worker node: {worker_node_url}")
                    async with worker_node as node:
                        consumer = await node.register_user(user_input=consumer)
                        logger.info(f"User registered: {consumer} on worker node: {worker_node_url}")

    async def start_run(self):
        logger.info("Starting orchestrator run")
        self.orchestrator_run.status = "running"
        await update_db_with_status_sync(module_run=self.orchestrator_run)

        try:
            response = await maybe_async_call(
                self.orchestrator_func,
                orchestrator_run=self.orchestrator_run,
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

        self.orchestrator_run.results = [response]
        self.orchestrator_run.status = "completed"

    async def complete(self):
        self.orchestrator_run.status = "completed"
        self.orchestrator_run.error = False
        self.orchestrator_run.error_message = ""
        self.orchestrator_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.orchestrator_run.duration = (
            datetime.fromisoformat(self.orchestrator_run.completed_time)
            - datetime.fromisoformat(self.orchestrator_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(module_run=self.orchestrator_run)
        logger.info("Orchestrator run completed")

    async def fail(self):
        logger.error("Error running flow")
        error_details = traceback.format_exc()
        logger.error(f"Traceback: {error_details}")
        self.orchestrator_run.status = "error"
        self.orchestrator_run.error = True
        self.orchestrator_run.error_message = error_details
        self.orchestrator_run.completed_time = datetime.now(pytz.utc).isoformat()
        self.orchestrator_run.duration = (
            datetime.fromisoformat(self.orchestrator_run.completed_time)
            - datetime.fromisoformat(self.orchestrator_run.start_processing_time)
        ).total_seconds()
        await update_db_with_status_sync(orchestrator_run=self.orchestrator_run)
