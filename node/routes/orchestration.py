from fastapi import APIRouter
from node.schemas import Job
from node.storage.db.db import DB
from node.utils import get_logger
from typing import Dict

logger = get_logger(__name__)

router = APIRouter()

@router.post("/CreateTaskRun")
async def create_task_run(task_run: Job):
    db = await DB()
    job = await db.create_job(task_run)
    task_run = task_run[0]
    logger.info(f"Created task run: {task_run}")
    return task_run

@router.post("/UpdateTaskRun")
async def update_task_run(task_run: Job):
    db = await DB()
    updated_task_run = await db.update_job(task_run["id"], task_run)
    logger.info(f"Updated task run: {updated_task_run}")
    return updated_task_run