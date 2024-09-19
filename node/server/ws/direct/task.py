import json
import asyncio
from datetime import datetime
from node.utils import get_logger
from node.storage.hub.hub import Hub
from node.storage.db.db import DB
from naptha_sdk.schemas import DockerParams, ModuleRunInput
from node.worker.docker_worker import execute_docker_module
from node.worker.template_worker import run_flow
import os

logger = get_logger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

async def create_task(data: str) -> str:
    try:
        job = json.loads(data)
        logger.info(f"Processing job: {job}")

        module_run_input = ModuleRunInput(**job)

        async with Hub() as hub:
            success, user, user_id = await hub.signin(os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD"))
            module = await hub.list_modules(f"module:{module_run_input.module_name}")
            
            if not module:
                return json.dumps({"status": "error", "message": "Module not found"})
            
            module_run_input.module_type = module["type"]
            module_run_input.module_version = module["version"]
            module_run_input.module_url = module["url"]
            
            if module["type"] == "docker":
                module_run_input.module_params = DockerParams(**module_run_input.module_params)

        async with DB() as db:
            module_run = await db.create_module_run(module_run_input)
            logger.info("Created module run")

        # Execute the task
        if module_run.module_type in ["flow", "template"]:
            task = run_flow.delay(module_run.dict())
        elif module_run.module_type == "docker":
            task = execute_docker_module.delay(module_run.dict())
        else:
            return json.dumps({"status": "error", "message": "Invalid module type"})

        # Wait for the task to complete
        while not task.ready():
            await asyncio.sleep(1)

        # Retrieve the updated module run from the database
        async with DB() as db:
            updated_module_run = await db.list_module_runs(module_run.id)
            
        if updated_module_run:
            # Convert the Pydantic model to a dictionary with datetime objects serialized
            updated_module_run_dict = updated_module_run.dict()
        
            return json.dumps({"status": "success", "data": updated_module_run_dict}, cls=DateTimeEncoder)
        else:
            return json.dumps({"status": "error", "message": "Failed to retrieve updated module run"})

    except Exception as e:
        logger.error(f"Error processing job: {str(e)}")
        return json.dumps({"status": "error", "message": str(e)})