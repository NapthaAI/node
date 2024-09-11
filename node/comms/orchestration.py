from naptha_sdk.schemas import ModuleRun, ModuleRunInput
from node.storage.db.db import DB
from node.utils import get_logger
import traceback
from typing import Dict
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import asyncio

logger = get_logger(__name__)

# Define a custom exception for transient errors
class TransientDatabaseError(Exception):
    pass

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=0.5, max=10),
    retry=retry_if_exception_type(TransientDatabaseError),
    before_sleep=lambda retry_state: logger.info(f"Retrying operation, attempt {retry_state.attempt_number}")
)
async def create_task_run(module_run_input: ModuleRunInput) -> ModuleRun:
    try:
        logger.info(f"Creating module run for worker node {module_run_input.worker_nodes[0]}: {module_run_input}")
        async with DB() as db:
            module_run = await db.create_module_run(module_run_input)
        logger.info(f"Created module run for worker node {module_run_input.worker_nodes[0]}: {module_run}")
        return module_run
    except Exception as e:
        logger.error(f"Failed to create module run for worker node {module_run_input.worker_nodes[0]}: {module_run_input}")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        if isinstance(e, asyncio.TimeoutError) or "Resource busy" in str(e):
            raise TransientDatabaseError(str(e))
        raise Exception(f"Failed to create module run for worker node {module_run_input.worker_nodes[0]}: {module_run_input}")

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=0.5, max=10),
    retry=retry_if_exception_type(TransientDatabaseError),
    before_sleep=lambda retry_state: logger.info(f"Retrying operation, attempt {retry_state.attempt_number}")
)
async def update_task_run(module_run: ModuleRun) -> ModuleRun:
    try:
        logger.info(f"Updating module run for worker node {module_run.worker_nodes[0]}: {module_run}")
        async with DB() as db:
            try:
                updated_module_run = await db.update_module_run(module_run.id, module_run)
                logger.info(f"Updated module run for worker node {module_run.worker_nodes[0]}: {updated_module_run}")
                return updated_module_run
            except Exception as db_error:
                logger.error(f"Database operation failed: {str(db_error)}")
                if isinstance(db_error, asyncio.TimeoutError) or "Resource busy" in str(db_error):
                    raise TransientDatabaseError(str(db_error))
                raise
    except Exception as e:
        logger.error(f"Failed to update module run for worker node {module_run.worker_nodes[0]}: {module_run}")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        if not isinstance(e, TransientDatabaseError):
            raise Exception(f"Failed to update module run: {str(e)}")
        raise