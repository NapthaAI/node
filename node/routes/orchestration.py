from fastapi import APIRouter
from node.schemas import ModuleRun, ModuleRunInput
from node.storage.db.db import DB
from node.utils import get_logger
from typing import Dict

logger = get_logger(__name__)

router = APIRouter()

@router.post("/CreateTaskRun")
async def create_task_run(module_run_input: ModuleRunInput) -> ModuleRun:
    db = await DB()
    module_run = await db.create_module_run(module_run_input)
    logger.info(f"Created module run: {module_run}")
    return module_run

@router.post("/UpdateTaskRun")
async def update_task_run(module_run: ModuleRun) -> ModuleRun:
    logger.info(f"Updating module run: {module_run}")
    db = await DB()
    updated_module_run = await db.update_module_run(module_run.id, module_run)
    logger.info(f"Updated module run: {updated_module_run}")
    return updated_module_run

