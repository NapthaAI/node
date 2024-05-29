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
from node.celery_worker.utils import load_yaml_config, MODULES_PATH, prepare_input_dir, update_db_with_status_sync
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
    workflow_engine = FlowEngine(job)
    workflow_engine.init_run()
    try:
        asyncio.run(workflow_engine.start_run())
        while True:
            if workflow_engine.job["status"] == "error":
                workflow_engine.fail()
                break
            else:
                workflow_engine.complete()
                break
            time.sleep(3)


class FlowEngine:
    def __init__(self, job):
        self.job = job
        self.flow = None
        self.flow_name = job["module_id"]
        self.parameters = job["module_params"]
        self.task_results = []

        if hasattr(job, 'coworkers') and job['coworkers'] is not None:
            self.nodes = [Node(coworker) for coworker in job['coworkers']]
        else:
            self.nodes = None

        self.consumer = {
            "public_key": job["consumer_id"].split(':')[1],
            'id': job["consumer_id"],
        }

    def init_run(self):
        logger.info(f"Initializing flow run: {self.job}")
        self.job["status"] = "processing"
        self.job["start_processing_time"] = datetime.now(pytz.utc).isoformat()
        self.job = {k: v for k, v in self.job.items() if v is not None} # remove None values from job
        asyncio.run(update_db_with_status_sync(job_data=self.job)) # Update the job status to processing

        self.flow = self.load_flow()

        if "input_dir" in self.parameters or "input_ipfs_hash" in self.parameters:
            self.parameters = prepare_input_dir(
                parameters=self.parameters,
                input_dir=self.parameters.get("input_dir", None),
                input_ipfs_hash=self.parameters.get("input_ipfs_hash", None)
            )

    async def start_run(self):
        logger.info(f"Starting flow run: {self.job}")
        self.state = "running"
        await update_db_with_status_sync(job_data=self.job)

        for node, task_name, args in self.flow.tasks:

            logger.info(f"Node: {node}, Task: {task_name}")

            logger.info(f"Checking user: {self.consumer}")
            consumer = await node.check_user(user_input=self.consumer)

            if consumer["is_registered"] == True:
                logger.info("Found user...", consumer)
            elif consumer["is_registered"] == False:
                logger.info("No user found. Registering user...")
                consumer = await node.register_user(user_input=consumer)
                logger.info(f"User registered: {consumer}.")

            print('Args: ', args)

            task_input = {
                'consumer_id': consumer["id"],
                "module_id": task_name,
                "module_params": args,
            }

            logger.info(f"Running task: {task_input}")
            job = await node.run_task(task_input=task_input, local=True)
            logger.info(f"Flow run: {job}")
            while True:
                j = await node.check_task({"id": job['id']})

                status = j['status']
                logger.info(status)   

                if status == 'completed':
                    break
                if status == 'error':
                    break

                time.sleep(3)

            if j['status'] == 'completed':
                logger.info(j['reply'])
                task_result = j['reply']
                self.add_task_result(task_result)
            else:
                logger.info(j['error_message'])
                self.fail(j['error_message'])
                break

    def complete(self):
        self.job["status"] = "completed"
        self.job["reply"] = out_msg
        self.job["error"] = False
        self.job["error_message"] = ""
        self.job["completed_time"] = datetime.now(pytz.timezone("UTC")).isoformat()
        self.job["duration"] = self.job["completed_time"] - self.job["start_processing_time"]
        asyncio.run(update_db_with_status_sync(job_data=self.job))
        logger.info(f"Flow run completed: {job}")

    def fail(self):
        logger.error(f"Error running template job")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        self.job["status"] = "error"
        self.job["status"] = "error"
        self.job["error"] = True
        self.job["error_message"] = error_details
        self.job["completed_time"] = datetime.now(pytz.timezone("UTC")).isoformat()
        self.job["duration"] = self.job["completed_time"] - self.job["start_processing_time"]
        asyncio.run(update_db_with_status_sync(job_data=self.job))

    def add_task_result(self, task_result):
        self.task_results.append(task_result.to_dict())

    def load_and_validate_input_schema(self):
        tn = self.flow_name.replace("-", "_")
        schemas_module = importlib.import_module(f"{tn}.schemas")
        InputSchema = getattr(schemas_module, "InputSchema")
        return InputSchema(**self.parameters)

    def load_flow(self):
        workflow_path = f"{MODULES_PATH}/{self.flow_name}"
        cfg = load_yaml_config(f"{workflow_path}/{self.flow_name}/component.yaml")
        validated_data = self.load_and_validate_input_schema()
        tn = self.flow_name.replace("-", "_")
        entrypoint = cfg["implementation"]["package"]["entrypoint"].split(".")[0]
        main_module = importlib.import_module(f"{tn}.run")
        main_func = getattr(main_module, entrypoint)
        return main_func(validated_data, self.nodes, self.job, cfg=cfg)

    def save_workflow_result(self):
        pass