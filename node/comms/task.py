from node.worker.docker_worker import execute_docker_module
from node.worker.template_worker import run_flow
from node.storage.hub.hub import Hub
from node.storage.db.db import DB
from naptha_sdk.schemas import DockerParams, ModuleRun, ModuleRunInput
from node.utils import get_logger, get_config
import traceback

logger = get_logger(__name__)

BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]


# Endpoint to receive a task
async def create_task(module_run_input: ModuleRunInput) -> ModuleRun:
    """
    Create a Task
    :param module_run_input: Module run specifications
    :return: Status
    """
    try:
        logger.info(f"Received task: {module_run_input}")

        hub = await Hub()
        module = await hub.list_modules(f"module:{module_run_input.module_name}")
        logger.info(f"Found module: {module}")

        if not module:
            raise Exception("Module not found")

        module_run_input.module_type = module["type"]

        if module["type"] == "docker":
            module_run_input.module_params = DockerParams(**module_run_input.module_params)

        db = await DB()
        module_run = await db.create_module_run(module_run_input)
        logger.info(f"Created module run: {module_run}")

        updated_module_run = await db.update_module_run(module_run.id, module_run)
        logger.info(f"Updated module run: {updated_module_run}")

        # Enqueue the module run in Celery
        if module_run.module_type in ["flow", "template"]:
            run_flow.delay(module_run.dict())
        elif module_run.module_type == "docker":
            execute_docker_module.delay(module_run.dict())
        else:
            raise Exception("Invalid module type")

        return module_run

    except Exception as e:
        logger.error(f"Failed to run module: {str(e)}")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        raise Exception(f"Failed to run module: {module_run}")


async def check_task(module_run: ModuleRun) -> ModuleRun:
    """
    Check a task
    :param module_run: ModuleRun details
    :return: Status
    """
    logger.info(f"Checking task: {module_run}")

    db = await DB()
    module_run = await db.list_module_runs(module_run.id)

    logger.info(f"Found task: {module_run}")

    status = module_run.status
    logger.info(f"Found task status: {status}")

    response = None
    if module_run.status == "completed":
        logger.info(f"Task completed. Returning output: {module_run.results}")
        response = module_run.results
        logger.info(f"Response: {response}")
    elif module_run.status == "error":
        logger.info(f"Task failed. Returning error: {module_run.error_message}")
        response = module_run.error_message
        logger.info(f"Response: {response}")

    return module_run
