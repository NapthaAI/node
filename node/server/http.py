from fastapi import FastAPI, APIRouter, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import uvicorn
import io
from typing import Optional
from naptha_sdk.schemas import ModuleRun, ModuleRunInput, TaskRun, TaskRunInput

from node.utils import get_logger
from node.server.task import create_task, check_task
from node.server.storage import write_to_ipfs, read_from_ipfs_or_ipns, write_storage, read_storage
from node.server.user import check_user, register_user
from node.server.orchestration import create_task_run, update_task_run

logger = get_logger(__name__)

class HTTPServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        
        self.app = FastAPI()
        
        router = APIRouter()

        # Task endpoints
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

        # Storage endpoints
        @router.post("/write_storage")
        async def write_storage_http(file: UploadFile = File(...)):
            """Write files to the storage."""
            status_code, message_dict = await write_storage(file)
            return JSONResponse(status_code=status_code, content=message_dict)

        @router.get("/read_storage/{job_id}")
        async def read_storage_http(job_id: str):
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
        async def write_to_ipfs_http(
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
        async def read_from_ipfs_or_ipns_http(hash_or_name: str):
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
        async def check_user_http(user_input: dict):
            """Check if a user exists."""
            return await check_user(user_input)

        @router.post("/register_user")
        async def register_user_http(user_input: dict):
            """Register a new user."""
            return await register_user(user_input)

        # Orchestration endpoints
        @router.post("/create_task_run")
        async def create_task_run_http(task_run_input: TaskRunInput) -> TaskRun:
            """Create a new task run."""
            return await create_task_run(task_run_input)

        @router.post("/update_task_run")
        async def update_task_run_http(task_run: TaskRun) -> TaskRun:
            """Update an existing task run."""
            return await update_task_run(task_run)

        # Include the router
        self.app.include_router(router)

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

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