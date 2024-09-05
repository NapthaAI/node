from naptha_sdk.schemas import ModuleRun, ModuleRunInput
from node.storage.db.db import DB
from node.utils import get_logger
import traceback
from typing import Dict

logger = get_logger(__name__)


async def create_task_run(module_run_input: ModuleRunInput) -> ModuleRun:
    try:
        logger.info(f"Creating module run for worker node {module_run_input.worker_nodes[0]}: {module_run_input}")
        db = DB()
        module_run = await db.create_module_run(module_run_input)
        logger.info(f"Created module run for worker node {module_run_input.worker_nodes[0]}: {module_run}")
        return module_run
    except Exception as e:
        logger.error(f"Failed to create module run for worker node {module_run_input.worker_nodes[0]}: {module_run_input}")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        raise Exception(f"Failed to create module run for worker node {module_run_input.worker_nodes[0]}: {module_run_input}")

async def update_task_run(module_run: ModuleRun) -> ModuleRun:
    try:
        logger.info(f"Updating module run for worker node {module_run.worker_nodes[0]}: {module_run}")
        db = DB()
        updated_module_run = await db.update_module_run(module_run.id, module_run)
        logger.info(f"Updated module run for worker node {module_run.worker_nodes[0]}: {updated_module_run}")
        return updated_module_run
    except Exception as e:
        logger.error(f"Failed to update module run for worker node {module_run.worker_nodes[0]}: {module_run}")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        raise Exception(f"Failed to update module run for worker node {module_run.worker_nodes[0]}: {module_run}")