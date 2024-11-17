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
from pydantic import BaseModel
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
from node.module_manager import install_agent_if_not_present, install_personas_if_needed
from node.schemas import AgentRun
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
def run_flow(self, agent_run):
    try:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run_flow_async(agent_run))
    finally:
        # Force cleanup of channels
        app.backend.cleanup()

@app.task(bind=True, acks_late=True)
def run_agent(self, agent_run):
    try:
        agent_run = AgentRun(**agent_run)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run_agent_async(agent_run))
    finally:
        # Force cleanup of channels
        app.backend.cleanup()

async def _run_flow_async(agent_run: Dict) -> None:
    try:
        agent_run = AgentRun(**agent_run)
        agent_version = f"v{agent_run.agent_deployment.module['version']}"

        logger.info(f"Received flow run: {agent_run}")
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
            await handle_failure(agent_run, error_msg)
            return

        logger.info(
            f"Agent {agent_run.agent_deployment.module['name']} version {agent_version} is installed and verified. Initializing workflow engine..."
        )
        workflow_engine = FlowEngine(agent_run)

        await workflow_engine.init_run()
        await workflow_engine.start_run()

        if workflow_engine.agent_run.status == "completed":
            await workflow_engine.complete()
        elif workflow_engine.agent_run.status == "error":
            await workflow_engine.fail()
    except Exception as e:
        error_msg = f"Error in _run_flow_async: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        await handle_failure(agent_run, error_msg)
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
            await handle_failure(agent_run, error_msg)
            return

        logger.info(
            f"Agent {agent_run.agent_deployment.module['name']} version {agent_version} is installed and verified."
        )

        logger.info(f"Starting agent run")
        async with Node(agent_run.agent_deployment.worker_node_url, "http") as worker_node:
            agent_run = await worker_node.run_agent(agent_run_input=agent_run)

    except Exception as e:
        error_msg = f"Error in _run_agent_async: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        await handle_failure(agent_run, error_msg)
        return

async def handle_failure(agent_run: AgentRun, error_msg: str) -> None:
    agent_run.status = "error"
    agent_run.error = True
    agent_run.error_message = error_msg
    agent_run.completed_time = datetime.now(pytz.utc).isoformat()
    if (
        hasattr(agent_run, "start_processing_time")
        and agent_run.start_processing_time
    ):
        agent_run.duration = (
            datetime.fromisoformat(agent_run.completed_time)
            - datetime.fromisoformat(agent_run.start_processing_time)
        ).total_seconds()
    else:
        agent_run.duration = 0

    try:
        await update_db_with_status_sync(agent_run)
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


class FlowEngine:
    def __init__(self, agent_run: AgentRun):
        self.agent_run = agent_run
        self.flow = None
        self.flow_name = agent_run.agent_deployment.module["id"].split(":")[-1]
        self.parameters = agent_run.inputs
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

        if self.agent_run.agent_deployment.agent_config.persona_module:
            self.personas_urls = self.agent_run.agent_deployment.agent_config.persona_module["url"]

        self.consumer = {
            "public_key": agent_run.consumer_id.split(":")[1],
            "id": agent_run.consumer_id,
        }

    async def init_run(self):
        logger.info("Initializing flow run")
        self.agent_run.status = "processing"
        self.agent_run.start_processing_time = datetime.now(
            pytz.timezone("UTC")
        ).isoformat()

        await update_db_with_status_sync(agent_run=self.agent_run)

        if "input_dir" in self.parameters or "input_ipfs_hash" in self.parameters:
            self.parameters = prepare_input_dir(
                parameters=self.parameters,
                input_dir=self.parameters.get("input_dir", None),
                input_ipfs_hash=self.parameters.get("input_ipfs_hash", None),
            )

        # Check if the user has the right to use the worker nodes if not register the user
        if self.agent_run.agent_deployment.worker_node_url:
            await self.check_register_worker_nodes(self.agent_run.agent_deployment.worker_node_url)

        # Install the personas if needed
        if self.personas_urls:
            logger.info(f"Installing personas for agent {self.flow_name}: {self.personas_urls}")
            await install_personas_if_needed(self.flow_name, self.personas_urls)
            logger.info(f"Personas installed for agent {self.flow_name}")

        # Load the flow
        self.flow_func, self.validated_data, self.cfg = await self.load_flow()

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
        
    async def check_register_worker_nodes(self, worker_node_urls: List[str]):
        """
        Checks if the user has the right to use the worker nodes
        """
        logger.info(f"Checking user: {self.consumer} on worker nodes: {worker_node_urls}")
        for worker_node_url in worker_node_urls:
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

    async def handle_ipfs_output(self, cfg, results):
        """
        Handles the outputs of the flow
        """
        save_location = self.parameters.get("save_location", None)
        if save_location:
            self.cfg["outputs"]["location"] = save_location

        if self.cfg["outputs"]["save"]:
            if self.cfg["outputs"]["location"] == "ipfs":
                out_msg = upload_to_ipfs(self.parameters["output_path"])
                out_msg = f"IPFS Hash: {out_msg}"
                logger.info(f"Output uploaded to IPFS: {out_msg}")
                self.agent_run.results = [out_msg]

    async def start_run(self):
        logger.info("Starting flow run")
        self.agent_run.status = "running"
        await update_db_with_status_sync(agent_run=self.agent_run)

        try:
            response = await maybe_async_call(
                self.flow_func,
                inputs=self.validated_data,
                worker_node_urls=self.agent_run.agent_deployment.worker_node_urls,
                orchestrator_node=self.orchestrator_node,
                cfg=self.cfg,
                agent_run=self.agent_run,
                task_engine_cls=TaskEngine,
                node_cls=Node,
                db_url=LOCAL_DB_URL,
                agents_dir=AGENTS_SOURCE_DIR,
            )
        except Exception as e:
            logger.error(f"Error running flow: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

        logger.info(f"Flow run response: {response}")

        if isinstance(response, (dict, list, tuple)):
            response = json.dumps(response)
        elif isinstance(response, BaseModel):
            response = response.model_dump_json()

        if not isinstance(response, str):
            raise ValueError(
                f"Agent/flow response is not a string: {response}. Current response type: {type(response)}"
            )

        self.agent_run.results = [response]
        await self.handle_ipfs_output(self.cfg, response)
        self.agent_run.status = "completed"

    async def complete(self):
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
        logger.error("Error running flow")
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

    def load_and_validate_input_schema(self):
        tn = self.flow_name.replace("-", "_")
        schemas_module = importlib.import_module(f"{tn}.schemas")
        InputSchema = getattr(schemas_module, "InputSchema")
        return InputSchema(**self.parameters)

    async def upload_input_params_to_ipfs(self, validated_data):
        """
        Uploads the input parameters to IPFS
        """
        ipfs_hash = upload_json_string_to_ipfs(validated_data.model_dump_json())
        return ipfs_hash

    async def load_flow(self):
        """
        Loads the flow from the agent and returns the workflow
        """
        # Load the flow from the agent
        workflow_path = f"{AGENTS_SOURCE_DIR}/{self.flow_name}"

        # Load the component.yaml file
        cfg = load_yaml_config(f"{workflow_path}/{self.flow_name}/component.yaml")

        # If the output is set to save, save the output to the outputs folder
        if cfg["outputs"]["save"]:
            if ':' in self.agent_run.id:
                output_path = f"{BASE_OUTPUT_DIR}/{self.agent_run.id.split(':')[1]}"
            else:
                output_path = f"{BASE_OUTPUT_DIR}/{self.agent_run.id}"
            self.parameters["output_path"] = output_path
            if not os.path.exists(output_path):
                os.makedirs(output_path)

        validated_data = self.load_and_validate_input_schema()
        # add code to upload input params to ipfs if needed
        tn = self.flow_name.replace("-", "_")
        entrypoint = cfg["implementation"]["package"]["entrypoint"].split(".")[0]
        main_module = importlib.import_module(f"{tn}.run")
        main_module = importlib.reload(main_module)
        flow_func = getattr(main_module, entrypoint)
        return flow_func, validated_data, cfg
