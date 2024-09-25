import os
import sys
import pytz
import json
import fcntl
import time
import functools
import inspect
import asyncio
import requests
import importlib
import subprocess
import traceback
import importlib
from git import Repo
from typing import Dict
from pathlib import Path
from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv
from contextlib import contextmanager
from git.exc import GitCommandError, InvalidGitRepositoryError
from node.worker.utils import (
    load_yaml_config, 
    prepare_input_dir, 
    update_db_with_status_sync, 
    upload_to_ipfs, 
    upload_json_string_to_ipfs
)
from node.worker.main import app
from node.engine.ws.node import Node as WsNode
from node.engine.ws.node import NodeIndirect as WsNodeIndirect
from naptha_sdk.client.node import Node
from node.schemas import AgentRun
from node.utils import get_logger
from node.config import BASE_OUTPUT_DIR, AGENTS_SOURCE_DIR, NODE_TYPE, NODE_IP, NODE_PORT, NODE_ROUTING, SERVER_TYPE

logger = get_logger(__name__)

# Load environment variables
load_dotenv(".env")
os.environ["BASE_OUTPUT_DIR"] = f"{BASE_OUTPUT_DIR}"


if AGENTS_SOURCE_DIR not in sys.path:
    sys.path.append(AGENTS_SOURCE_DIR)

class LockAcquisitionError(Exception):
    pass

@contextmanager
def file_lock(lock_file, timeout=30):
    lock_fd = None
    try:
        # Ensure the directory exists
        lock_dir = os.path.dirname(lock_file)
        os.makedirs(lock_dir, exist_ok=True)
        
        start_time = time.time()
        while True:
            try:
                lock_fd = open(lock_file, 'w')
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except IOError:
                if time.time() - start_time > timeout:
                    raise LockAcquisitionError(f"Failed to acquire lock after {timeout} seconds")
                time.sleep(1)
        
        yield lock_fd

    finally:
        if lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

@app.task
def run_flow(flow_run: Dict) -> None:
    asyncio.run(_run_flow_async(flow_run))

async def install_agent_if_not_present(flow_run_obj, agent_version):
    agent_name = flow_run_obj.agent_name
    lock_file = Path(AGENTS_SOURCE_DIR) / f"{agent_name}.lock"
    logger.info(f"Lock file: {lock_file}")
    try:
        with file_lock(lock_file):
            logger.info(f"Acquired lock for {agent_name}")

            if not is_agent_installed(agent_name, agent_version):
                logger.info(f"Agent {agent_name} version {agent_version} is not installed. Attempting to install...")
                if not flow_run_obj.agent_source_url:
                    raise ValueError(f"Agent URL is required for installation of {agent_name}")
                install_agent_if_needed(agent_name, agent_version, flow_run_obj.agent_source_url)
            
            # Verify agent installation
            if not verify_agent_installation(agent_name):
                raise RuntimeError(f"Agent {agent_name} failed verification after installation")
            
            logger.info(f"Agent {agent_name} version {agent_version} is installed and verified")

    except LockAcquisitionError as e:
        error_msg = f"Failed to acquire lock for agent {agent_name}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = f"Failed to install or verify agent {agent_name}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e

async def _run_flow_async(flow_run: Dict) -> None:
    try:
        flow_run_obj = AgentRun(**flow_run)
        agent_version = f"v{flow_run_obj.agent_version}"

        logger.info(f"Received flow run: {flow_run_obj}")
        logger.info(f"Checking if agent {flow_run_obj.agent_name} version {agent_version} is installed")
        
        try:
            await install_agent_if_not_present(flow_run_obj, agent_version)
        except Exception as e:
            error_msg = f"Failed to install or verify agent {flow_run_obj.agent_name}: {str(e)}"
            logger.error(error_msg)
            if "Dependency conflict detected" in str(e):
                logger.error("This error is likely due to a mismatch in naptha-sdk versions. Please check and align the versions in both the agent and the main project.")
            await handle_failure(flow_run, error_msg)
            return
        
        logger.info(f"Agent {flow_run_obj.agent_name} version {agent_version} is installed and verified. Initializing workflow engine...")
        workflow_engine = FlowEngine(flow_run_obj)

        await workflow_engine.init_run()
        await workflow_engine.start_run()
        
        if workflow_engine.flow_run.status == "completed":
            await workflow_engine.complete()
        elif workflow_engine.flow_run.status == "error":
            await workflow_engine.fail()
    except Exception as e:
        error_msg = f"Error in _run_flow_async: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        await handle_failure(flow_run, error_msg)

async def handle_failure(flow_run: Dict, error_msg: str) -> None:
    flow_run_obj = AgentRun(**flow_run)
    flow_run_obj.status = "error"
    flow_run_obj.error = True
    flow_run_obj.error_message = error_msg
    flow_run_obj.completed_time = datetime.now(pytz.timezone("UTC")).isoformat()
    if hasattr(flow_run_obj, 'start_processing_time') and flow_run_obj.start_processing_time:
        flow_run_obj.duration = (datetime.fromisoformat(flow_run_obj.completed_time) - 
                                 datetime.fromisoformat(flow_run_obj.start_processing_time)).total_seconds()
    else:
        flow_run_obj.duration = 0
    
    try:
        await update_db_with_status_sync(flow_run_obj)
    except Exception as db_error:
        logger.error(f"Failed to update database after error: {str(db_error)}")

def is_agent_installed(agent_name: str, required_version: str) -> bool:
    try:
        agent = importlib.import_module(agent_name)
        agents_source_dir = os.path.join(AGENTS_SOURCE_DIR, agent_name)

        if not Path(agents_source_dir).exists():
            logger.warning(f"Agents source directory for {agent_name} does not exist")
            return False
            
        try:
            repo = Repo(agents_source_dir)
            if repo.head.is_detached:
                current_tag = next((tag.name for tag in repo.tags if tag.commit == repo.head.commit), None)
            else:
                current_tag = next((tag.name for tag in repo.tags if tag.commit == repo.head.commit), None)
            
            if current_tag:
                logger.info(f"Agent {agent_name} is at tag: {current_tag}")
                current_version = current_tag[1:] if current_tag.startswith('v') else current_tag
                required_version = required_version[1:] if required_version.startswith('v') else required_version
                return current_version == required_version
            else:
                logger.warning(f"No tag found for current commit in {agent_name}")
                return False
        except (InvalidGitRepositoryError, GitCommandError) as e:
            logger.error(f"Git error for {agent_name}: {str(e)}")
            return False
        
    except ImportError:
        logger.warning(f"Agent {agent_name} not found")
        return False

def run_poetry_command(command):
    try:
        result = subprocess.run(["poetry"] + command, check=True, capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        error_msg = f"Poetry command failed: {e.cmd}"
        logger.error(error_msg)
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        raise RuntimeError(error_msg)

def verify_agent_installation(agent_name: str) -> bool:
    try:
        importlib.import_module(f"{agent_name}.run")
        return True
    except ImportError as e:
        logger.error(f"Error importing agent {agent_name}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    
def install_agent_if_needed(agent_name: str, agent_version: str, agent_source_url: str):
    logger.info(f"Installing/updating agent {agent_name} version {agent_version}")
    
    agents_source_dir = Path(AGENTS_SOURCE_DIR) / agent_name
    logger.info(f"Agent path exists: {agents_source_dir.exists()}")

    try:
        if agents_source_dir.exists():
            logger.info(f"Updating existing repository for {agent_name}")
            repo = Repo(agents_source_dir)
            repo.remotes.origin.fetch()
            repo.git.checkout(agent_version)
            logger.info(f"Successfully updated {agent_name} to version {agent_version}")
        else:
            # Clone new repository
            logger.info(f"Cloning new repository for {agent_name}")
            Repo.clone_from(agent_source_url, agents_source_dir)
            repo = Repo(agents_source_dir)
            repo.git.checkout(agent_version)
            logger.info(f"Successfully cloned {agent_name} version {agent_version}")

        # Reinstall the agent
        logger.info(f"Installing/Reinstalling {agent_name}")
        installation_output = run_poetry_command(["add", f"{agents_source_dir}"])
        logger.info(f"Installation output: {installation_output}")

        if not verify_agent_installation(agent_name):
            raise RuntimeError(f"Agent {agent_name} failed verification after installation")

        logger.info(f"Successfully installed and verified {agent_name} version {agent_version}")
    except Exception as e:
        error_msg = f"Error installing {agent_name}: {str(e)}"
        logger.error(error_msg)
        logger.info(f"Traceback: {traceback.format_exc()}")
        if "Dependency conflict detected" in str(e):
            error_msg += "\nThis is likely due to a mismatch in naptha-sdk versions between the agent and the main project."
        raise RuntimeError(error_msg) from e

async def maybe_async_call(func, *args, **kwargs):
    if inspect.iscoroutinefunction(func):
        # If it's an async function, await it directly
        return await func(*args, **kwargs)
    else:
        # If it's a sync function, run it in an executor to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))

class FlowEngine:
    def __init__(self, flow_run: AgentRun):
        self.flow_run = flow_run
        self.flow = None
        self.flow_name = flow_run.agent_name
        self.parameters = flow_run.agent_run_params
        self.node_type = NODE_TYPE
        self.server_type = SERVER_TYPE
        if self.node_type == "direct" and self.server_type == "http":
            self.orchestrator_node = Node(f'{NODE_IP}:{NODE_PORT}')
            logger.info(f"Orchestrator node: {self.orchestrator_node.node_url}")
        elif self.node_type == "direct" and self.server_type == "ws":
            ip = NODE_IP
            if 'http' in ip:
                ip = ip.replace('http://', 'ws://')
            self.orchestrator_node = WsNode(f'{ip}:{NODE_PORT}')
            logger.info(f"Orchestrator node: {self.orchestrator_node.node_url}")
        elif self.node_type == "indirect":
            node_id = requests.get("http://localhost:7001/node_id").json()
            if not node_id:
                raise ValueError("NODE_ID environment variable is not set")
            self.orchestrator_node = Node(
                indirect_node_id=node_id,
                routing_url=NODE_ROUTING
            )
        else:
            raise ValueError(f"Invalid NODE_TYPE: {self.node_type}")

        if flow_run.worker_nodes is not None:
            self.worker_nodes = []
            for worker_node in flow_run.worker_nodes:
                if 'ws' in worker_node:
                    self.worker_nodes.append(WsNode(worker_node))
                elif ":" not in worker_node:
                    self.worker_nodes.append(WsNodeIndirect(worker_node, routing_url=NODE_ROUTING))
                else:
                    self.worker_nodes.append(Node(worker_node))
        else:
            self.worker_nodes = None

        logger.info(f"Worker Nodes: {self.worker_nodes}")

        self.consumer = {
            "public_key": flow_run.consumer_id.split(':')[1],
            'id': flow_run.consumer_id,
        }

    async def init_run(self):
        logger.info("Initializing flow run")
        self.flow_run.status = "processing"
        self.flow_run.start_processing_time = datetime.now(pytz.utc).isoformat()
        await update_db_with_status_sync(agent_run=self.flow_run)

        if "input_dir" in self.parameters or "input_ipfs_hash" in self.parameters:
            self.parameters = prepare_input_dir(
                parameters=self.parameters,
                input_dir=self.parameters.get("input_dir", None),
                input_ipfs_hash=self.parameters.get("input_ipfs_hash", None)
            )

        self.flow_func, self.validated_data, self.cfg = await self.load_flow()

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
                self.flow_run.results = [out_msg]

    async def start_run(self):
        logger.info("Starting flow run")
        self.flow_run.status = "running"
        await update_db_with_status_sync(agent_run=self.flow_run)

        try:
            response = await maybe_async_call(
                self.flow_func,
                inputs=self.validated_data, 
                worker_nodes=self.worker_nodes,
                orchestrator_node=self.orchestrator_node, 
                flow_run=self.flow_run, 
                cfg=self.cfg
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
            raise ValueError(f"Agent/flow response is not a string: {response}. Current response type: {type(response)}")

        self.flow_run.results = [response]
        await self.handle_ipfs_output(self.cfg, response)
        self.flow_run.status = "completed"

    async def complete(self):
        self.flow_run.status = "completed"
        self.flow_run.error = False
        self.flow_run.error_message = ""
        self.flow_run.completed_time = datetime.now(pytz.timezone("UTC")).isoformat()
        self.flow_run.duration = (datetime.fromisoformat(self.flow_run.completed_time) - datetime.fromisoformat(self.flow_run.start_processing_time)).total_seconds()
        await update_db_with_status_sync(agent_run=self.flow_run)
        logger.info(f"Agent run completed")

    async def fail(self):
        logger.error("Error running flow")
        error_details = traceback.format_exc()
        logger.error(f"Traceback: {error_details}")
        self.flow_run.status = "error"
        self.flow_run.error = True
        self.flow_run.error_message = error_details
        self.flow_run.completed_time = datetime.now(pytz.timezone("UTC")).isoformat()
        self.flow_run.duration = (datetime.fromisoformat(self.flow_run.completed_time) - datetime.fromisoformat(self.flow_run.start_processing_time)).total_seconds()
        await update_db_with_status_sync(agent_run=self.flow_run)

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
            output_path = f"{BASE_OUTPUT_DIR}/{self.flow_run.id.split(':')[1]}"
            self.parameters["output_path"] = output_path
            if not os.path.exists(output_path):
                os.makedirs(output_path)

        validated_data = self.load_and_validate_input_schema()
        self.flow_run.input_schema_ipfs_hash = await self.upload_input_params_to_ipfs(validated_data)
        tn = self.flow_name.replace("-", "_")
        entrypoint = cfg["implementation"]["package"]["entrypoint"].split(".")[0]
        main_module = importlib.import_module(f"{tn}.run")
        main_module = importlib.reload(main_module)
        flow_func = getattr(main_module, entrypoint)
        return flow_func, validated_data, cfg