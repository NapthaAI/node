from fastapi import APIRouter
from naptha_sdk.schemas import  ModuleRun, ModuleRunInput
from node.utils import get_logger, get_config
from node.server.task import create_task, check_task


logger = get_logger(__name__)


router = APIRouter()


BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]


# Endpoint to receive a task
@router.post("/CreateTask")
async def create_task_http(module_run_input: ModuleRunInput) -> ModuleRun:
    """
    Create a Task
    :param module_run_input: Module run specifications
    :return: Status
    """
    return await create_task(module_run_input)


@router.post("/CheckTask")
async def check_task_http(module_run: ModuleRun) -> ModuleRun:
    """
    Check a task
    :param module_run: ModuleRun details
    :return: Status
    """
    return await check_task(module_run)
