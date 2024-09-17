from dotenv import load_dotenv
from node.worker.docker_worker import execute_docker_module
from node.worker.template_worker import run_flow
from node.storage.hub.hub import Hub
from node.storage.db.db import DB
from naptha_sdk.schemas import DockerParams, ModuleRun, ModuleRunInput
from node.utils import get_logger, get_config
import os
import traceback
from fastapi import HTTPException

logger = get_logger(__name__)
load_dotenv()
BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]


async def create_task(module_run_input: ModuleRunInput) -> ModuleRun:
    """
    Create a Task
    :param module_run_input: Module run specifications
    :return: Status
    """
    try:
        logger.info(f"Received task: {module_run_input}")

        async with Hub() as hub:
            success, user, user_id = await hub.signin(os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD"))
            module = await hub.list_modules(f"module:{module_run_input.module_name}")
            logger.info(f"Found module: {module}")

            if not module:
                raise HTTPException(status_code=404, detail="Module not found")

            module_run_input.module_type = module["type"]
            module_run_input.module_version = module["version"]
            module_run_input.module_url = module["url"]

            if module["type"] == "docker":
                module_run_input.module_params = DockerParams(**module_run_input.module_params)

        async with DB() as db:
            module_run = await db.create_module_run(module_run_input)
            logger.info("Created module run")

            updated_module_run = await db.update_module_run(module_run.id, module_run)
            logger.info("Updated module run")

        # Enqueue the module run in Celery
        if module_run.module_type in ["flow", "template"]:
            run_flow.delay(module_run.dict())
        elif module_run.module_type == "docker":
            execute_docker_module.delay(module_run.dict())
        else:
            raise HTTPException(status_code=400, detail="Invalid module type")

        return module_run

    except Exception as e:
        logger.error(f"Failed to run module: {str(e)}")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        raise HTTPException(status_code=500, detail=f"Failed to run module: {module_run_input}")


async def check_task(module_run: ModuleRun) -> ModuleRun:
    """
    Check a task
    :param module_run: ModuleRun details
    :return: Status
    """
    try:
        logger.info("Checking task")
        id_ = module_run.id
        if id_ is None:
            raise HTTPException(status_code=400, detail="Module run ID is required")

        async with DB() as db:
            module_run = await db.list_module_runs(id_)

        if not module_run:
            raise HTTPException(status_code=404, detail="Task not found")

        status = module_run.status
        logger.info(f"Found task status: {status}")

        if module_run.status == "completed":
            logger.info(f"Task completed. Returning output: {module_run.results}")
            response = module_run.results
        elif module_run.status == "error":
            logger.info(f"Task failed. Returning error: {module_run.error_message}")
            response = module_run.error_message
        else:
            response = None

        logger.info(f"Response: {response}")

        return module_run

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check task: {str(e)}")
        logger.debug(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error occurred while checking task")

