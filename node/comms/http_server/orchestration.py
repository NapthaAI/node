from fastapi import APIRouter
from naptha_sdk.schemas import ModuleRun, ModuleRunInput
from node.utils import get_logger
from node.comms.orchestration import create_task_run, update_task_run

logger = get_logger(__name__)


router = APIRouter()


@router.post("/CreateTaskRun")
async def create_task_run_http(module_run_input: ModuleRunInput) -> ModuleRun:
    return await create_task_run(module_run_input)


@router.post("/UpdateTaskRun")
async def update_task_run_http(module_run: ModuleRun) -> ModuleRun:
    return await update_task_run(module_run)

