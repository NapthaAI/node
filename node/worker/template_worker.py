import os
import sys
import pytz
import json
import functools
import inspect
import asyncio
import requests
import importlib
import traceback
import logging
from typing import Dict, List
from pathlib import Path
from pydantic import BaseModel, create_model
from datetime import datetime
from dotenv import load_dotenv

from node.client import Node
from node.config import (
    BASE_OUTPUT_DIR,
    AGENTS_SOURCE_DIR,
    NODE_TYPE,
    NODE_IP,
    NODE_PORT,
    NODE_ROUTING,
    SERVER_TYPE,
    LOCAL_DB_URL,
)
from node.module_manager import (
    load_agent, 
    load_orchestrator,
    install_agent_if_not_present, 
)
from node.schemas import (
    AgentRun,
    OrchestratorRun,
)
from node.worker.main import app
from node.worker.task_engine import TaskEngine
from node.worker.utils import (
    load_yaml_config,
    prepare_input_dir,
    update_db_with_status_sync,
    upload_to_ipfs,
    upload_json_string_to_ipfs,
)

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(".env")
os.environ["BASE_OUTPUT_DIR"] = f"{BASE_OUTPUT_DIR}"


if AGENTS_SOURCE_DIR not in sys.path:
    sys.path.append(AGENTS_SOURCE_DIR)


@app.task(bind=True, acks_late=True)
def run_agent(self, agent_run):
    try:
        agent_run = AgentRun(**agent_run)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run_agent_async(agent_run))
    finally:
        # Force cleanup of channels
        app.backend.cleanup()

@app.task(bind=True, acks_late=True)
def run_orchestrator(self, orchestrator_run):
    try:
        orchestrator_run = OrchestratorRun(**orchestrator_run)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run_orchestrator_async(orchestrator_run))
    finally:
        # Force cleanup of channels
        app.backend.cleanup()

async def _run_orchestrator_async(orchestrator_run: Dict) -> None:
    try:
        orchestrator_version = f"v{orchestrator_run.orchestrator_deployment.module['version']}"

        logger.info(f"Received orchestrator run: {orchestrator_run}")
        logger.info(
            f"Checking if orchestrator {orchestrator_run.orchestrator_deployment.module["name"]} version {orchestrator_version} is installed"
        )

        try:
            await install_agent_if_not_present(orchestrator_run, orchestrator_version)
        except Exception as e:
            error_msg = (
                f"Failed to install or verify orchestrator {orchestrator_run.orchestrator_deployment.module['name']}: {str(e)}"
            )
            logger.error(error_msg)
            if "Dependency conflict detected" in str(e):
                logger.error(
                    "This error is likely due to a mismatch in naptha-sdk versions. Please check and align the versions in both the agent and the main project."
                )
            await handle_failure(
                error_msg=error_msg, 
                orchestrator_run=orchestrator_run
            )
            return

        logger.info(
            f"Orchestrator {orchestrator_run.orchestrator_deployment.module['name']} version {orchestrator_version} is installed and verified. Initializing workflow engine..."
        )
        workflow_engine = OrchestratorEngine(orchestrator_run)

        await workflow_engine.init_run()
        await workflow_engine.start_run()

        if workflow_engine.orchestrator_run.status == "completed":
            await workflow_engine.complete()
        elif workflow_engine.orchestrator_run.status == "error":
            await workflow_engine.fail()
    except Exception as e:
        error_msg = f"Error in _run_orchestrator_async: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        await handle_failure(
            error_msg=error_msg, 
            orchestrator_run=orchestrator_run
        )
        return

async def _run_agent_async(agent_run: AgentRun) -> None:
    try:
        agent_version = f"v{agent_run.agent_deployment.module['version']}"

        logger.info(f"Received agent run: {agent_run}")
        logger.info(
            f"Checking if agent {agent_run.agent_deployment.module["name"]} version {agent_version} is installed"
        )

        try:
            await install_agent_if_not_present(agent_run, agent_version)
        except Exception as e:
            error_msg = (
                f"Failed to install or verify agent {agent_run.agent_deployment.module['name']}: {str(e)}"
            )
            logger.error(error_msg)
            if "Dependency conflict detected" in str(e):
                logger.error(
                    "This error is likely due to a mismatch in naptha-sdk versions. Please check and align the versions in both the agent and the main project."
                )
            await handle_failure(
                error_msg=error_msg, 
                agent_run=agent_run
            )
            return

        logger.info(
            f"Agent {agent_run.agent_deployment.module['name']} version {agent_version} is installed and verified."
        )

        logger.info(f"Starting agent run")

        workflow_engine = AgentEngine(agent_run)
        await workflow_engine.init_run()
        await workflow_engine.start_run()

        if workflow_engine.agent_run.status == "completed":
            await workflow_engine.complete()
        elif workflow_engine.agent_run.status == "error":
            await workflow_engine.fail()

    except Exception as e:
        error_msg = f"Error in _run_agent_async: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        await handle_failure(
            error_msg=error_msg, 
            agent_run=agent_run
        )
        return

async def handle_failure(
        error_msg: str, 
        agent_run: AgentRun = None, 
        orchestrator_run: OrchestratorRun = None
    ) -> None:
    if agent_run:
        agent_run.status = "error"
        agent_run.error = True
        agent_run.error_message = error_msg
        agent_run.completed_time = datetime.now(pytz.utc).isoformat()
        if hasattr(agent_run, "start_processing_time") and agent_run.start_processing_time:
            agent_run.duration = (
                datetime.fromisoformat(agent_run.completed_time)
                - datetime.fromisoformat(agent_run.start_processing_time)
            ).total_seconds()
        else:
            agent_run.duration = 0

        try:
            await update_db_with_status_sync(agent_run=agent_run)
        except Exception as db_error:
            logger.error(f"Failed to update database after error: {str(db_error)}")

    if orchestrator_run:
        orchestrator_run.status = "error"
        orchestrator_run.error = True
        orchestrator_run.error_message = error_msg
        orchestrator_run.completed_time = datetime.now(pytz.utc).isoformat()
        if hasattr(orchestrator_run, "start_processing_time") and orchestrator_run.start_processing_time:
            orchestrator_run.duration = (
                datetime.fromisoformat(orchestrator_run.completed_time)
                - datetime.fromisoformat(orchestrator_run.start_processing_time)
            ).total_seconds()
        else:
            orchestrator_run.duration = 0
        try:
            await update_db_with_status_sync(orchestrator_run=orchestrator_run)
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
        self.agent_version = f"v{self.module['version']}"
        self.parameters = agent_run.inputs

        if self.agent_run.agent_deployment.agent_config.persona_module:
            self.personas_url = self.agent_run.agent_deployment.agent_config.persona_module["url"]

        self.consumer = {
            "public_key": agent_run.consumer_id.split(":")[1],
            "id": agent_run.consumer_id,
        }

    async def init_run(self):
        logger.info("Initializing agent run")
        self.agent_run.status = "processing"
        self.agent_run.start_processing_time = datetime.now(pytz.timezone("UTC")).isoformat()

        await update_db_with_status_sync(agent_run=self.agent_run)

        if "input_dir" in self.parameters or "input_ipfs_hash" in self.parameters:
            self.parameters = prepare_input_dir(
                parameters=self.parameters,
                input_dir=self.parameters.get("input_dir", None),
                input_ipfs_hash=self.parameters.get("input_ipfs_hash", None),
            )

        # Load the agent
        self.agent_func, self.agent_run = await load_agent(self.agent_run)

    async def start_run(self):
        """Executes the agent run"""
        logger.info("Starting agent run")
        self.agent_run.status = "running"
        await update_db_with_status_sync(agent_run=self.agent_run)

        logger.info(f"Agent deployment: {self.agent_run.agent_deployment}")

        try:
            response = await maybe_async_call(
                self.agent_func,
                agent_run=self.agent_run,
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
            raise ValueError(
                f"Agent response is not a string: {response}. Current response type: {type(response)}"
            )

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
        await update_db_with_status_sync(agent_run=self.agent_run)
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
        await update_db_with_status_sync(agent_run=self.agent_run)


class OrchestratorEngine:
    def __init__(self, orchestrator_run: OrchestratorRun):
        self.orchestrator_run = orchestrator_run
        self.orchestrator_name = orchestrator_run.orchestrator_deployment.module["name"]
        self.orchestrator_version = f"v{orchestrator_run.orchestrator_deployment.module['version']}"
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

        # set environment url TODO: here override the environment url. is this correct?
        self.orchestrator_run.environment_deployments[0].environment_node_url = LOCAL_DB_URL


    async def init_run(self):
        logger.info("Initializing orchestrator run")
        self.orchestrator_run.status = "processing"
        self.orchestrator_run.start_processing_time = datetime.now(
            pytz.timezone("UTC")
        ).isoformat()

        await update_db_with_status_sync(orchestrator_run=self.orchestrator_run)

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
        await self.check_register_worker_nodes(self.orchestrator_run.agent_deployments)

        # Load the orchestrator
        (
            self.orchestrator_func, 
            self.orchestrator_run, 
            self.validated_data, 
        ) = await load_orchestrator(
            orchestrator_run=self.orchestrator_run,
            agent_source_dir=AGENTS_SOURCE_DIR
        )
        

    def node_url_to_node(self, node_url: str):
        """
        Converts the node url to a node object
        """
        if 'ws://' in node_url:
            return Node(node_url=node_url, server_type='ws')
        elif 'http://' in node_url:
            return Node(node_url=node_url, server_type='http')
        elif '://' not in node_url:
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

    # TODO: do we need to handle output at the orchestrator level?
    # async def handle_ipfs_output(self, cfg, results):
    #     """
    #     Handles the outputs of the orchestrator
    #     """
    #     save_location = self.parameters.get("save_location", None)
    #     if save_location:
    #         self.cfg["outputs"]["location"] = save_location

    #     if self.cfg["outputs"]["save"]:
    #         if self.cfg["outputs"]["location"] == "ipfs":
    #             out_msg = upload_to_ipfs(self.parameters["output_path"])
    #             out_msg = f"IPFS Hash: {out_msg}"
    #             logger.info(f"Output uploaded to IPFS: {out_msg}")
    #             self.orchestrator_run.results = [out_msg]

    async def start_run(self):
        logger.info("Starting orchestrator run")
        self.orchestrator_run.status = "running"
        await update_db_with_status_sync(orchestrator_run=self.orchestrator_run)

        try:
            response = await maybe_async_call(
                self.orchestrator_func,
                orchestrator_run=self.orchestrator_run,
                task_engine_cls=TaskEngine,
                node_cls=Node,
                db_url=LOCAL_DB_URL,
                agents_dir=AGENTS_SOURCE_DIR,
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
            raise ValueError(
                f"Agent/orchestrator response is not a string: {response}. Current response type: {type(response)}"
            )

        self.orchestrator_run.results = [response]

        # await self.handle_ipfs_output(self.cfg, response)
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
        await update_db_with_status_sync(orchestrator_run=self.orchestrator_run)
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

    async def upload_input_params_to_ipfs(self, validated_data):
        """
        Uploads the input parameters to IPFS
        """
        ipfs_hash = upload_json_string_to_ipfs(validated_data.model_dump_json())
        return ipfs_hash