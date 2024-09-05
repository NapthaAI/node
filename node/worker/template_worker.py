import os
import sys
import pytz
import json
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
from git.exc import GitCommandError, InvalidGitRepositoryError
from node.worker.utils import (
    load_yaml_config, 
    MODULES_PATH, 
    BASE_OUTPUT_DIR,
    prepare_input_dir, 
    update_db_with_status_sync, 
    upload_to_ipfs, 
    upload_json_string_to_ipfs
)
from node.worker.main import app
from naptha_sdk.client.node import Node
from naptha_sdk.schemas import ModuleRun
from node.utils import get_logger

logger = get_logger(__name__)

# Load environment variables
load_dotenv(".env")
os.environ["BASE_OUTPUT_DIR"] = f"{BASE_OUTPUT_DIR}"

if MODULES_PATH not in sys.path:
    sys.path.append(MODULES_PATH)


@app.task
def run_flow(flow_run: Dict) -> None:
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(_run_flow_async(flow_run))
    except Exception as e:
        error_msg = f"Error in run_flow: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        loop.run_until_complete(handle_failure(flow_run, error_msg))

async def _run_flow_async(flow_run: Dict) -> None:
    flow_run_obj = ModuleRun(**flow_run)
    module_version = f"v{flow_run_obj.module_version}"

    logger.info(f"Received flow run: {flow_run_obj}")
    logger.info(f"Checking if module {flow_run_obj.module_name} version {module_version} is installed")
    
    if not is_module_installed(flow_run_obj.module_name, module_version):
        logger.info(f"Module {flow_run_obj.module_name} version {module_version} is not installed. Attempting to install...")
        if not flow_run_obj.module_url:
            raise ValueError(f"Module URL is required for installation of {flow_run_obj.module_name}")
        install_module_if_needed(flow_run_obj.module_name, module_version, flow_run_obj.module_url)
    
    logger.info(f"Module {flow_run_obj.module_name} version {module_version} is installed. Initializing workflow engine...")
    workflow_engine = FlowEngine(flow_run_obj)

    await workflow_engine.init_run()
    await workflow_engine.start_run()
    
    if workflow_engine.flow_run.status == "completed":
        await workflow_engine.complete()
    elif workflow_engine.flow_run.status == "error":
        await workflow_engine.fail()

async def handle_failure(flow_run: Dict, error_msg: str) -> None:
    flow_run_obj = ModuleRun(**flow_run)
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

def is_module_installed(module_name: str, required_version: str) -> bool:
    try:
        module = importlib.import_module(module_name)
        module_path = os.path.join(MODULES_PATH, module_name)

        if module_path:
            raise Exception("Error for fun")

        if not Path(module_path).exists():
            logger.warning(f"Module directory for {module_name} does not exist")
            return False
            
        try:
            repo = Repo(module_path)
            if repo.head.is_detached:
                current_tag = next((tag.name for tag in repo.tags if tag.commit == repo.head.commit), None)
            else:
                current_tag = next((tag.name for tag in repo.tags if tag.commit == repo.head.commit), None)
            
            if current_tag:
                logger.info(f"Module {module_name} is at tag: {current_tag}")
                # Remove 'v' prefix if present for comparison
                current_version = current_tag[1:] if current_tag.startswith('v') else current_tag
                required_version = required_version[1:] if required_version.startswith('v') else required_version
                return current_version == required_version
            else:
                logger.warning(f"No tag found for current commit in {module_name}")
                return False
        except (InvalidGitRepositoryError, GitCommandError) as e:
            logger.error(f"Git error for {module_name}: {str(e)}")
            return False
        
    except ImportError:
        logger.warning(f"Module {module_name} not found")
        return False

def run_poetry_command(command):
    try:
        subprocess.run(["poetry"] + command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        error_msg = f"Poetry command failed: {e.cmd}"
        logger.error(error_msg)
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        raise RuntimeError(error_msg)

def install_module_if_needed(module_name: str, module_version: str, module_url: str):
    if not module_url:
        raise ValueError(f"Module URL is required for installation of {module_name}")

    logger.info(f"Installing/updating module {module_name} version {module_version}")
    
    module_path = Path(MODULES_PATH) / module_name
    logger.info(f"Module path exists: {module_path.exists()}")
    try:
        if module_path.exists():
            logger.info(f"Uninstalling existing {module_name}")
            run_poetry_command(["remove", module_name])
            repo = Repo(module_path)
            logger.info(f"Updating existing repository for {module_name}")
            repo.remotes.origin.fetch()
            repo.git.checkout(module_version)
            logger.info(f"Successfully updated {module_name} to version {module_version}")

        else:
            # Clone new repository
            logger.info(f"Cloning new repository for {module_name}")
            Repo.clone_from(module_url, module_path)
            repo = Repo(module_path)
            repo.git.checkout(module_version)
            logger.info(f"Successfully cloned {module_name} version {module_version}")

        # Reinstall the module
        logger.info(f"Installing/Reinstalling {module_name}")
        run_poetry_command(["add", f"{module_path}"])

        logger.info(f"Successfully installed {module_name} version {module_version}")        
    except GitCommandError as e:
        error_msg = f"Git operation failed for {module_name}: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    except Exception as e:
        error_msg = f"Error installing {module_name}: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

class FlowEngine:
    def __init__(self, flow_run: ModuleRun):
        self.flow_run = flow_run
        self.flow = None
        self.flow_name = flow_run.module_name
        self.parameters = flow_run.module_params
        self.node_type = os.getenv("NODE_TYPE")
        if self.node_type == "direct":
            self.orchestrator_node = Node(f'{os.getenv("NODE_IP")}:{os.getenv("NODE_PORT")}')
            logger.info(f"Orchestrator node: {self.orchestrator_node.node_url}")
        else:
            node_id = requests.get("http://localhost:7001/node_id").json()
            if not node_id:
                raise ValueError("NODE_ID environment variable is not set")
            self.orchestrator_node = Node(
                indirect_node_id=node_id,
                routing_url=os.getenv("NODE_ROUTING")
            )

        if flow_run.worker_nodes is not None:
            self.worker_nodes = [Node(worker_node) for worker_node in flow_run.worker_nodes]
        else:
            self.worker_nodes = None

        logger.info(f"Worker Nodes: {self.worker_nodes}")

        self.consumer = {
            "public_key": flow_run.consumer_id.split(':')[1],
            'id': flow_run.consumer_id,
        }

    async def init_run(self):
        logger.info(f"Initializing flow run: {self.flow_run}")
        self.flow_run.status = "processing"
        self.flow_run.start_processing_time = datetime.now(pytz.utc).isoformat()
        await update_db_with_status_sync(module_run=self.flow_run)

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
        logger.info(f"Starting flow run: {self.flow_run}")
        self.flow_run.status = "running"
        await update_db_with_status_sync(module_run=self.flow_run)

        if inspect.iscoroutinefunction(self.flow_func):
            response = await self.flow_func(
                inputs=self.validated_data, 
                worker_nodes=self.worker_nodes,
                orchestrator_node=self.orchestrator_node, 
                flow_run=self.flow_run, 
                cfg=self.cfg
            )
        else:
            response = self.flow_func(
                inputs=self.validated_data, 
                worker_nodes=self.worker_nodes,
                orchestrator_node=self.orchestrator_node, 
                flow_run=self.flow_run, 
                cfg=self.cfg
            )
        logger.info(f"Flow run response: {response}")

        if isinstance(response, (dict, list, tuple)):
            response = json.dumps(response)

        if isinstance(response, BaseModel):
            response = response.model_dump_json()

        # if response if not a string, raise an error
        if not isinstance(response, str):
            raise ValueError(f"Module/flow response is not a string: {response}. Current response type: {type(response)}")

        self.flow_run.results = [response]
        await self.handle_ipfs_output(self.cfg, response)
        self.flow_run.status = "completed"

    async def complete(self):
        self.flow_run.status = "completed"
        self.flow_run.error = False
        self.flow_run.error_message = ""
        self.flow_run.completed_time = datetime.now(pytz.timezone("UTC")).isoformat()
        self.flow_run.duration = (datetime.fromisoformat(self.flow_run.completed_time) - datetime.fromisoformat(self.flow_run.start_processing_time)).total_seconds()
        await update_db_with_status_sync(module_run=self.flow_run)
        logger.info(f"Flow run completed: {self.flow_run}")

    async def fail(self):
        logger.error("Error running flow")
        error_details = traceback.format_exc()
        logger.error(f"Traceback: {error_details}")
        self.flow_run.status = "error"
        self.flow_run.error = True
        self.flow_run.error_message = error_details
        self.flow_run.completed_time = datetime.now(pytz.timezone("UTC")).isoformat()
        self.flow_run.duration = (datetime.fromisoformat(self.flow_run.completed_time) - datetime.fromisoformat(self.flow_run.start_processing_time)).total_seconds()
        await update_db_with_status_sync(module_run=self.flow_run)

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
        Loads the flow from the module and returns the workflow
        """
        # Load the flow from the module
        workflow_path = f"{MODULES_PATH}/{self.flow_name}"

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