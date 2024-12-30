import asyncio
import functools
import inspect
import json
import logging
import os
import pytz
import sys
import traceback
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Union

from node.config import BASE_OUTPUT_DIR, MODULES_SOURCE_DIR
from node.module_manager import install_module_with_lock, load_module
from node.schemas import AgentRun, MemoryRun, ToolRun, EnvironmentRun, OrchestratorRun, KBRun
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
def run_memory(self, memory_run):
    try:
        memory_run = MemoryRun(**memory_run)
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(_run_module_async(memory_run))
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

async def _run_module_async(module_run: Union[AgentRun, MemoryRun, ToolRun, OrchestratorRun, EnvironmentRun, KBRun]) -> None:
    """Handles execution of agent, memory, orchestrator, and environment runs.
    
    Args:
        module_run: Either an AgentRun, MemoryRun, OrchestratorRun, or EnvironmentRun object
    """
    try:
        module_run_engine = ModuleRunEngine(module_run)

        module_version = f"v{module_run_engine.module['module_version']}"
        module_name = module_run_engine.module["name"]
        module = module_run.deployment.module

        logger.info(f"Received {module_run_engine.module_type} run: {module_run}")
        logger.info(f"Checking if {module_run_engine.module_type} {module_name} version {module_version} is installed")

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
    def __init__(self, module_run: Union[AgentRun, MemoryRun, ToolRun, EnvironmentRun, KBRun]):
        self.module_run = module_run
        self.deployment = module_run.deployment
        self.module = self.deployment.module

        # Determine module type
        if isinstance(module_run, AgentRun):
            self.module_type = "agent"
        elif isinstance(module_run, MemoryRun):
            self.module_type = "memory"
        elif isinstance(module_run, OrchestratorRun):
            self.module_type = "orchestrator"
        elif isinstance(module_run, ToolRun):
            self.module_type = "tool"
        elif isinstance(module_run, EnvironmentRun):
            self.module_type = "environment"
        elif isinstance(module_run, KBRun):
            self.module_type = "knowledge_base"
        else:
            raise ValueError(f"Invalid module run type: {type(module_run)}")

        self.module_name = self.module["name"]
        self.module_version = f"v{self.module['module_version']}"
        self.parameters = module_run.inputs

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
        self.module_func, self.module_run = await load_module(self.module_run)

    async def start_run(self):
        """Executes the module run"""
        logger.info(f"Starting {self.module_type} run")
        self.module_run.status = "running"
        await update_db_with_status_sync(module_run=self.module_run)

        logger.info(f"{self.module_type.title()} deployment: {self.deployment}")

        try:
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
            await self.handle_output(self.module_run, response)
            
        self.module_run.status = "completed"

    async def handle_output(self, module_run, results):
        """Handles the output of the module run (only for agent and tool runs)"""
        if module_run.deployment.data_generation_config:
            save_location = module_run.deployment.data_generation_config.save_outputs_location
            if save_location:
                module_run.deployment.data_generation_config.save_outputs_location = save_location

            if module_run.deployment.data_generation_config.save_outputs:
                if save_location == "node":
                    if ':' in module_run.id:
                        output_path = f"{BASE_OUTPUT_DIR}/{module_run.id.split(':')[1]}"
                    else:
                        output_path = f"{BASE_OUTPUT_DIR}/{module_run.id}"
                    module_run.deployment.data_generation_config.save_outputs_path = output_path
                    if not os.path.exists(output_path):
                        os.makedirs(output_path)
                elif save_location == "ipfs":
                    save_path = getattr(module_run.deployment.data_generation_config, "save_outputs_path")
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
