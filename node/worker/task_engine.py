from datetime import datetime
from node.schemas import AgentRun, AgentRunInput
from node.utils import get_logger
import pytz
import traceback
import asyncio
from node.storage.db.db import DB
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


logger = get_logger(__name__)
NUM_RETRIES = 10
BACKOFF_MULTIPLIER = 1
BACKOFF_MIN = 1
BACKOFF_MAX = 10

class TransientDatabaseError(Exception):
    pass


@retry(
    stop=stop_after_attempt(NUM_RETRIES),
    wait=wait_exponential(multiplier=BACKOFF_MULTIPLIER, min=BACKOFF_MIN, max=BACKOFF_MAX),
    retry=retry_if_exception_type(TransientDatabaseError),
    reraise=True
)
async def update_agent_run(task_run: AgentRun):
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
async def create_agent_run(task_run: AgentRun):
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
    def __init__(self, flow_run):
        self.flow_run = flow_run
        self.agent_result = None
        self.agent_run = None

        self.consumer = {
            "public_key": flow_run.consumer_id.split(':')[1],
            'id': flow_run.consumer_id,
        }

    async def init_run(self, task, parameters):
        self.task = task
        self.parameters = parameters
        if isinstance(self.flow_run, AgentRunInput):
            self.flow_run = await create_agent_run(self.flow_run)
            logger.info(f"flow_run: {self.flow_run}")

        agent_run_input = {
            'consumer_id': self.consumer["id"],
            "worker_nodes": [self.task.worker_node.node_url],
            "agent_name": self.task.fn,
            "agent_run_type": "package",
            "agent_run_params": self.parameters,
            "parent_runs": [{k: v for k, v in self.flow_run.model_dict().items() if k not in ["child_runs", "parent_runs"]}],
        }
        self.agent_run_input = AgentRunInput(**agent_run_input)
        logger.info(f"Initializing agent run.")
        self.agent_run = await create_agent_run(self.agent_run_input)
        self.agent_run.start_processing_time = datetime.now(pytz.utc).isoformat()

        # Relate new agent run with parent flow run
        self.flow_run.child_runs.append(AgentRun(**{k: v for k, v in self.agent_run.model_dict().items() if k not in ["child_runs", "parent_runs"]}))
        logger.info(f"Adding agent run to parent flow run: {self.flow_run}")

    async def start_run(self):
        logger.info(f"Starting agent run")
        self.agent_run.status = "running"

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

        logger.info(f"Running agent on worker node {self.task.worker_node.node_url}")
        async with self.task.worker_node as node:
            agent_run = await node.run_agent(agent_run_input=self.agent_run_input)
        logger.info(f"Completed agent run on worker node {self.task.worker_node.node_url}")

        self.agent_run = agent_run

        if self.agent_run.status == 'completed':
            logger.info(f"Agent run completed: {self.agent_run}")
            self.agent_result = self.agent_run.results
            return self.agent_run.results
        else:
            logger.info(f"Agent run failed: {self.agent_run}")
            return self.agent_run.error_message

    async def complete(self):
        self.agent_run.status = "completed"
        self.agent_run.results.extend(self.agent_result)
        self.flow_run.results.extend(self.agent_result)
        self.agent_run.error = False
        self.agent_run.error_message = ""
        self.agent_run.completed_time = datetime.now(pytz.utc).isoformat()
        
        start_time = self.agent_run.start_processing_time
        end_time = self.agent_run.completed_time

        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.rstrip('Z'))
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.rstrip('Z'))

        self.agent_run.duration = (end_time - start_time).total_seconds()
        await update_agent_run(self.agent_run)

    async def fail(self):
        logger.error(f"Error running agent")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        self.agent_run.status = "error"
        self.agent_run.error = True
        self.agent_run.error_message = error_details
        self.agent_run.completed_time = datetime.now(pytz.utc).isoformat()
        
        start_time = self.agent_run.start_processing_time
        end_time = self.agent_run.completed_time

        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.rstrip('Z'))
        if isinstance(end_time, str):
            end_time = datetime.fromisoformat(end_time.rstrip('Z'))

        self.agent_run.duration = (end_time - start_time).total_seconds()
        await update_agent_run(self.agent_run)