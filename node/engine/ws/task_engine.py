from datetime import datetime
from node.schemas import AgentRun, AgentRunInput
from naptha_sdk.utils import get_logger
import pytz
import traceback
import asyncio
from node.storage.db.db import DB
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


logger = get_logger(__name__)
NUM_RETRIES = 3
BACKOFF_MULTIPLIER = 1
BACKOFF_MIN = 1
BACKOFF_MAX = 10

async def run_task(task, flow_run, parameters) -> None:
    task_engine = TaskEngine(task, flow_run, parameters)
    await task_engine.init_run()
    try:
        result = await task_engine.start_run()
        if task_engine.task_run.status == "error":
            await task_engine.fail()
        else:
            await task_engine.complete()
        return result
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        await task_engine.fail()

        
class TransientDatabaseError(Exception):
    pass


@retry(
    stop=stop_after_attempt(NUM_RETRIES),
    wait=wait_exponential(multiplier=BACKOFF_MULTIPLIER, min=BACKOFF_MIN, max=BACKOFF_MAX),
    retry=retry_if_exception_type(TransientDatabaseError),
    reraise=True
)
async def update_task_run(task_run: AgentRun):
    try:
        logger.info("Updating agent run for worker node")
        async with DB() as db:
            updated_agent_run = await db.update_agent_run(task_run.id, task_run)
        logger.info("Updated agent run for worker node")
        return updated_agent_run
    except Exception as e:
        logger.error(f"Failed to update agent run: {str(e)}")
        logger.debug(f"Full traceback: {traceback.format_exc()}")
        if isinstance(e, asyncio.TimeoutError) or "Resource busy" in str(e):
            raise TransientDatabaseError(str(e))
        raise Exception(f"Internal server error occurred while updating agent run. {str(e)}")


@retry(
    stop=stop_after_attempt(NUM_RETRIES),
    wait=wait_exponential(multiplier=BACKOFF_MULTIPLIER, min=BACKOFF_MIN, max=BACKOFF_MAX),
    retry=retry_if_exception_type(TransientDatabaseError),
    reraise=True
)
async def create_task_run(task_run: AgentRun):
    try:
        logger.info(f"Creating agent run for worker node {task_run.worker_nodes[0]}")
        async with DB() as db:
            agent_run = await db.create_agent_run(task_run)
        logger.info(f"Created agent run for worker node {task_run.worker_nodes[0]}")
        return agent_run
    except Exception as e:
        logger.error(f"Failed to create agent run: {str(e)}")
        logger.debug(f"Full traceback: {traceback.format_exc()}")
        if isinstance(e, asyncio.TimeoutError) or "Resource busy" in str(e):
            raise TransientDatabaseError(str(e))
        raise Exception(f"Internal server error occurred while creating agent run. {str(e)}")

class TaskEngine:
    def __init__(self, task, flow_run, parameters):
        self.task = task
        self.flow_run = flow_run
        self.parameters = parameters
        self.task_result = None
        self.task_run = None

        self.consumer = {
            "public_key": flow_run.consumer_id.split(':')[1],
            'id': flow_run.consumer_id,
        }

    async def init_run(self):
        if isinstance(self.flow_run, AgentRunInput):
            self.flow_run = await create_task_run(self.flow_run)
            logger.info(f"flow_run: {self.flow_run}")

        task_run_input = {
            'consumer_id': self.consumer["id"],
            "worker_nodes": [self.task.worker_node.node_url],
            "agent_name": self.task.fn,
            "agent_run_type": "package",
            "agent_run_params": self.parameters,
            "parent_runs": [{k: v for k, v in self.flow_run.model_dict().items() if k not in ["child_runs", "parent_runs"]}],
        }
        self.task_run_input = AgentRunInput(**task_run_input)
        logger.info(f"Initializing task run.")
        self.task_run = await create_task_run(self.task_run_input)
        self.task_run.start_processing_time = datetime.now(pytz.utc).isoformat()

        # Relate new task run with parent flow run
        self.flow_run.child_runs.append(AgentRun(**{k: v for k, v in self.task_run.model_dict().items() if k not in ["child_runs", "parent_runs"]}))
        logger.info(f"Adding task run to parent flow run: {self.flow_run}")
        _ = await update_task_run(self.flow_run)

    async def start_run(self):
        logger.info(f"Starting task run: {self.task_run}")
        self.task_run.status = "running"
        await update_task_run(self.task_run)

        logger.info(f"Checking user: {self.consumer}")
        async with self.task.worker_node as node:
            consumer = await node.check_user(user_input=self.consumer)
        if consumer["is_registered"] == True:
            logger.info("Found user...", consumer)
        elif consumer["is_registered"] == False:
            logger.info("No user found. Registering user...")
            async with self.task.worker_node as node:
                consumer = await node.register_user(user_input=consumer)
            logger.info(f"User registered: {consumer}.")

        logger.info(f"Running task on worker node {self.task.worker_node.node_url}: {self.task_run_input}")
        async with self.task.worker_node as node:
            task_run = await node.run_agent(agent_run_input=self.task_run_input)
        logger.info(f"Completed task run on worker node {self.task.worker_node.node_url}: {task_run}")

        self.task_run = task_run

        await update_task_run(self.task_run)

        if self.task_run.status == 'completed':
            logger.info(f"Task run completed: {self.task_run}")
            self.task_result = self.task_run.results
            return self.task_run.results
        else:
            logger.info(f"Task run failed: {self.task_run}")
            return self.task_run.error_message

    async def complete(self):
        self.task_run.status = "completed"
        self.task_run.results.extend(self.task_result)
        self.flow_run.results.extend(self.task_result)
        self.task_run.error = False
        self.task_run.error_message = ""
        self.task_run.completed_time = datetime.now(pytz.utc)
        
        start_time = self.task_run.start_processing_time
        end_time = self.task_run.completed_time

        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.rstrip('Z'))
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.rstrip('Z'))

        self.task_run.duration = (end_time - start_time).total_seconds()
        await update_task_run(self.task_run)
        logger.info(f"Task run completed: {self.task_run}")

    async def fail(self):
        logger.error(f"Error running task")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        self.task_run.status = "error"
        self.task_run.error = True
        self.task_run.error_message = error_details
        self.task_run.completed_time = datetime.now(pytz.utc)
        
        start_time = self.task_run.start_processing_time
        end_time = self.task_run.completed_time

        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.rstrip('Z'))
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.rstrip('Z'))

        self.task_run.duration = (end_time - start_time).total_seconds()
        await update_task_run(self.task_run)