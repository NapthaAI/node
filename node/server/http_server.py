from fastapi import FastAPI, APIRouter, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import uvicorn
import io
import os
import traceback
from typing import Optional
from naptha_sdk.schemas import ModuleRun, ModuleRunInput, DockerParams

from node.utils import get_logger
from node.storage.storage import write_to_ipfs, read_from_ipfs_or_ipns, write_storage, read_storage
from node.user import check_user, register_user
from node.storage.hub.hub import Hub
from node.storage.db.db import DB
from node.worker.docker_worker import execute_docker_module
from node.worker.template_worker import run_flow
from dotenv import load_dotenv
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = get_logger(__name__)
load_dotenv()

class TransientDatabaseError(Exception):
    pass

class HTTPServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        
        self.app = FastAPI()
        
        router = APIRouter()

        # Task endpoints
        @router.post("/create_task")
        async def create_task_endpoint(module_run_input: ModuleRunInput) -> ModuleRun:
            """
            Create a Task
            :param module_run_input: Module run specifications
            :return: Status
            """
            return await self.create_task(module_run_input)

        @router.post("/check_task")
        async def check_task_endpoint(module_run: ModuleRun) -> ModuleRun:
            """
            Check a task
            :param module_run: ModuleRun details
            :return: Status
            """
            return await self.check_task(module_run)

        # Storage endpoints
        @router.post("/write_storage")
        async def write_storage_endpoint(file: UploadFile = File(...)):
            """Write files to the storage."""
            status_code, message_dict = await write_storage(file)
            return JSONResponse(status_code=status_code, content=message_dict)

        @router.get("/read_storage/{job_id}")
        async def read_storage_endpoint(job_id: str):
            """Get the output directory for a job_id and serve it as a tar.gz file."""
            status_code, message_dict = await read_storage(job_id)
            if status_code == 200:
                return FileResponse(
                    path=message_dict["path"],
                    media_type=message_dict["media_type"],
                    filename=message_dict["filename"],
                    headers=message_dict["headers"]
                )
            else:
                raise HTTPException(status_code=status_code, detail=message_dict["message"])

        @router.post("/write_ipfs")
        async def write_to_ipfs_endpoint(
            publish_to_ipns: bool = Form(False),
            update_ipns_name: Optional[str] = Form(None),
            file: UploadFile = File(...),
        ):
            """Write a file to IPFS, optionally publish to IPNS or update an existing IPNS record."""
            logger.info(f"Writing to IPFS: {file.filename}")
            logger.info(f"Publish to IPNS: {publish_to_ipns}")
            logger.info(f"Update IPNS name: {update_ipns_name}")
            status_code, message_dict = await write_to_ipfs(file, publish_to_ipns, update_ipns_name)
            logger.info(f"Status code: {status_code}")
            logger.info(f"Message dict: {message_dict}")

            if status_code == 201:
                return JSONResponse(status_code=status_code, content=message_dict)
            else:
                raise HTTPException(status_code=status_code, detail=message_dict["message"])

        @router.get("/read_ipfs/{hash_or_name}")
        async def read_from_ipfs_or_ipns_endpoint(hash_or_name: str):
            """Read a file from IPFS or IPNS."""
            status_code, message_dict = await read_from_ipfs_or_ipns(hash_or_name)
            if status_code == 200:
                if "content" in message_dict:
                    # For zipped directory content
                    return StreamingResponse(
                        io.BytesIO(message_dict["content"]),
                        media_type=message_dict["media_type"],
                        headers=message_dict["headers"]
                    )
                else:
                    # For single file content
                    return FileResponse(
                        path=message_dict["path"],
                        media_type=message_dict["media_type"],
                        filename=message_dict["filename"],
                        headers=message_dict["headers"]
                    )
            else:
                raise HTTPException(status_code=status_code, detail=message_dict["message"])

        # User endpoints
        @router.post("/check_user")
        async def check_user_endpoint(user_input: dict):
            """Check if a user exists."""
            return await check_user(user_input)

        @router.post("/register_user")
        async def register_user_endpoint(user_input: dict):
            """Register a new user."""
            return await register_user(user_input)

        # Orchestration endpoints
        @router.post("/create_task_run")
        async def create_task_run_endpoint(task_run_input: ModuleRunInput) -> ModuleRun:
            """Create a new task run."""
            return await self.create_task_run(task_run_input)

        @router.post("/update_task_run")
        async def update_task_run_endpoint(task_run: ModuleRun) -> ModuleRun:
            """Update an existing task run."""
            return await self.update_task_run(task_run)

        # Include the router
        self.app.include_router(router)

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    async def create_task(self, module_run_input: ModuleRunInput) -> ModuleRun:
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

    async def check_task(self, module_run: ModuleRun) -> ModuleRun:
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
        
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=0.5, max=10),
        retry=retry_if_exception_type(TransientDatabaseError),
        before_sleep=lambda retry_state: logger.info(f"Retrying operation, attempt {retry_state.attempt_number}")
    )
    async def create_task_run(self, task_run_input: ModuleRunInput) -> ModuleRun:
        try:
            logger.info(f"Creating task run for worker node {task_run_input.worker_nodes[0]}")
            async with DB() as db:
                task_run = await db.create_task_run(task_run_input)
            logger.info(f"Created task run for worker node {task_run_input.worker_nodes[0]}")
            return task_run
        except Exception as e:
            logger.error(f"Failed to create task run: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            if isinstance(e, asyncio.TimeoutError) or "Resource busy" in str(e):
                raise TransientDatabaseError(str(e))
            raise HTTPException(status_code=500, detail=f"Internal server error occurred while creating task run")

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=0.5, max=10),
        retry=retry_if_exception_type(TransientDatabaseError),
        before_sleep=lambda retry_state: logger.info(f"Retrying operation, attempt {retry_state.attempt_number}")
    )
    async def update_task_run(self, task_run: ModuleRun) -> ModuleRun:
        try:
            logger.info(f"Updating task run for worker node {task_run.worker_nodes[0]}")
            async with DB() as db:
                updated_task_run = await db.update_task_run(task_run.id, task_run)
            logger.info(f"Updated task run for worker node {task_run.worker_nodes[0]}")
            return updated_task_run
        except Exception as e:
            logger.error(f"Failed to update task run: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            if isinstance(e, asyncio.TimeoutError) or "Resource busy" in str(e):
                raise TransientDatabaseError(str(e))
            raise HTTPException(status_code=500, detail=f"Internal server error occurred while updating task run")

    async def launch_server(self):
        logger.info(f"Launching HTTP server...")
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="debug",
            timeout_keep_alive=300,
            limit_concurrency=200,
            backlog=4096,
        )
        server = uvicorn.Server(config)
        await server.serve()