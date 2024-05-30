import asyncio
from celery import Celery
from datetime import datetime
from dotenv import load_dotenv
import importlib
import json
import os
import pytz
import time
import traceback
from typing import Dict
from node.celery_worker.docker_manager import run_container_job
from node.celery_worker.template_manager import run_template_job
from node.celery_worker.utils import (
    load_yaml_config, 
    MODULES_PATH, 
    BASE_OUTPUT_DIR,
    prepare_input_dir, 
    update_db_with_status_sync, 
    upload_to_ipfs, 
    handle_ipfs_input
)
from node.nodes import Node
from node.utils import get_logger

logger = get_logger(__name__)

# Load environment variables
load_dotenv(".env")

# Celery config
BROKER_URL = os.environ.get("CELERY_BROKER_URL")

# Make sure OPENAI_API_KEY is set
try:
    OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
    logger.info("OPENAI_API_KEY found in environment")
except KeyError:
    logger.error("OPENAI_API_KEY not found in environment")
    raise Exception("OPENAI_API_KEY not found in environment")

# Celery app
app = Celery(
    "docker_tasks",
    broker=BROKER_URL,
)

# Function to execute a docker job
@app.task
def execute_docker_job(job: Dict) -> None:
    """
    Execute a docker job
    :param job: Job details
    :param hub_config: Hub config
    """

    logger.info(f"Executing docker job: {job}")

    job["status"] = "processing"
    job["start_processing_time"] = datetime.now(pytz.utc).isoformat()

    # Remove None values from job recursively
    def remove_none_values_from_dict(d):
        for key, value in list(d.items()):
            if value is None:
                del d[key]
            elif isinstance(value, dict):
                remove_none_values_from_dict(value)
        return d

    job = remove_none_values_from_dict(job)

    # Update the job status to processing
    asyncio.run(
        update_db_with_status_sync(
            job_data=job,
        )
    )
    try:
        run_container_job(
            job=job,
        )

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")


# Function to execute a template job
@app.task
def execute_template_job(job: Dict) -> None:
    """
    Execute a template job
    :param job: Job details
    :param hub_config: Hub config
    """

    logger.info(f"Executing template job: {job}")

    job["status"] = "processing"
    job["start_processing_time"] = datetime.now(pytz.utc).isoformat()

    # remove None values from job
    job = {k: v for k, v in job.items() if v is not None}

    # Update the job status to processing
    asyncio.run(
        update_db_with_status_sync(
            job_data=job,
        )
    )

    try:
        run_template_job(
            job=job,
        )

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")


@app.task
def run_flow(job: Dict) -> None:
    loop = asyncio.get_event_loop()
    workflow_engine = FlowEngine(job)
    loop.run_until_complete(workflow_engine.init_run())
    try:
        loop.run_until_complete(workflow_engine.start_run())
        while True:
            if workflow_engine.job["status"] == "error":
                loop.run_until_complete(workflow_engine.fail())
                break
            else:
                loop.run_until_complete(workflow_engine.complete())
                break
            time.sleep(3)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        loop.run_until_complete(workflow_engine.fail())


class FlowEngine:
    def __init__(self, job):
        self.job = job
        self.flow = None
        self.flow_name = job["module_id"]
        self.parameters = job["module_params"]
        self.task_results = []

        if ('coworkers' in job) and (job['coworkers'] is not None):
            self.nodes = [Node(coworker) for coworker in job['coworkers']]
        else:
            self.nodes = None

        logger.info(f"Nodes: {self.nodes}")

        self.consumer = {
            "public_key": job["consumer_id"].split(':')[1],
            'id': job["consumer_id"],
        }

    async def init_run(self):
        logger.info(f"Initializing flow run: {self.job}")
        self.job["status"] = "processing"
        self.job["start_processing_time"] = datetime.now(pytz.utc).isoformat()
        self.job = {k: v for k, v in self.job.items() if v is not None}
        await update_db_with_status_sync(job_data=self.job)

        self.flow_func, self.validated_data, self.cfg = await self.load_flow()

        if "input_dir" in self.parameters or "input_ipfs_hash" in self.parameters:
            self.parameters = prepare_input_dir(
                parameters=self.parameters,
                input_dir=self.parameters.get("input_dir", None),
                input_ipfs_hash=self.parameters.get("input_ipfs_hash", None)
            )

    async def handle_outputs(self):
        """
        Handles the outputs of the flow
        """
        save_location = self.parameters.get("save_location", None)
        if save_location:
            self.cfg["outputs"]["location"] = save_location

        if self.cfg["outputs"]["save"]:
            if self.cfg["outputs"]["location"] == "node":
                out_msg = {
                    "output": results
                }
            elif self.cfg["outputs"]["location"] == "ipfs":
                out_msg = upload_to_ipfs(self.parameters["output_path"])
                out_msg = f"IPFS Hash: {out_msg}"
                out_msg = {
                    "output": out_msg
                }
            else:
                raise ValueError(f"Invalid location: {cfg['outputs']['location']}")
        else:
            out_msg = {
                "output": results
            }

    async def start_run(self):
        logger.info(f"Starting flow run: {self.job}")
        self.state = "running"
        await update_db_with_status_sync(job_data=self.job)
        response = await self.flow_func(self.validated_data, self.nodes, self.job, cfg=self.cfg)

        # await self.handle_outputs()

    async def complete(self):
        self.job["status"] = "completed"
        self.job["reply"] = {"results": json.dumps(self.task_results)}
        self.job["error"] = False
        self.job["error_message"] = ""
        self.job["completed_time"] = datetime.now(pytz.timezone("UTC")).isoformat()
        self.job["duration"] = f"{(datetime.fromisoformat(self.job['completed_time']) - datetime.fromisoformat(self.job['start_processing_time'])).total_seconds()} seconds"
        await update_db_with_status_sync(job_data=self.job)
        logger.info(f"Flow run completed: {self.job}")

    async def fail(self):
        logger.error(f"Error running template job")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        self.job["status"] = "error"
        self.job["status"] = "error"
        self.job["error"] = True
        self.job["error_message"] = error_details
        self.job["completed_time"] = datetime.now(pytz.timezone("UTC")).isoformat()
        self.job["duration"] = f"{(datetime.fromisoformat(self.job['completed_time']) - datetime.fromisoformat(self.job['start_processing_time'])).total_seconds()} seconds"
        await update_db_with_status_sync(job_data=self.job)

    def load_and_validate_input_schema(self):
        tn = self.flow_name.replace("-", "_")
        schemas_module = importlib.import_module(f"{tn}.schemas")
        InputSchema = getattr(schemas_module, "InputSchema")
        return InputSchema(**self.parameters)

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
            output_path = f"{BASE_OUTPUT_DIR}/{self.job['id'].split(':')[1]}"
            self.parameters["output_path"] = output_path
            if not os.path.exists(output_path):
                os.makedirs(output_path)

        validated_data = self.load_and_validate_input_schema()
        tn = self.flow_name.replace("-", "_")
        entrypoint = cfg["implementation"]["package"]["entrypoint"].split(".")[0]
        main_module = importlib.import_module(f"{tn}.run")
        flow_func = getattr(main_module, entrypoint)
        return flow_func, validated_data, cfg