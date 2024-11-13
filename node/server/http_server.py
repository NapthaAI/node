from fastapi import FastAPI, APIRouter, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import uvicorn
import io
import os
import logging
import traceback
from datetime import datetime
from typing import Optional
from node.schemas import AgentRun, AgentRunInput, DockerParams

from node.storage.storage import (
    write_to_ipfs,
    read_from_ipfs_or_ipns,
    write_storage,
    read_storage,
)
from node.user import check_user, register_user
from node.storage.hub.hub import Hub
from node.storage.db.db import DB
from node.worker.docker_worker import execute_docker_agent
from node.worker.template_worker import run_flow
from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import asyncio

logger = logging.getLogger(__name__)
load_dotenv()


class TransientDatabaseError(Exception):
    pass


class HTTPServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

        self.app = FastAPI()

        router = APIRouter()

        @router.post("/agent/run")
        async def agent_run_endpoint(agent_run_input: AgentRunInput) -> AgentRun:
            """
            Run an agent
            :param agent_run_input: Agent run specifications
            :return: Status
            """
            return await self.agent_run(agent_run_input)

        @router.post("/agent/check")
        async def agent_check_endpoint(agent_run: AgentRun) -> AgentRun:
            """
            Check an agent
            :param agent_run: AgentRun details
            :return: Status
            """
            return await self.agent_check(agent_run)

        # Storage endpoints
        @router.post("/storage/write")
        async def storage_write_endpoint(file: UploadFile = File(...)):
            """Write files to the storage."""
            status_code, message_dict = await write_storage(file)
            return JSONResponse(status_code=status_code, content=message_dict)

        @router.get("/storage/read/{job_id}")
        async def storage_read_endpoint(job_id: str):
            """Get the output directory for a job_id and serve it as a tar.gz file."""
            status_code, message_dict = await read_storage(job_id)
            if status_code == 200:
                return FileResponse(
                    path=message_dict["path"],
                    media_type=message_dict["media_type"],
                    filename=message_dict["filename"],
                    headers=message_dict["headers"],
                )
            else:
                raise HTTPException(
                    status_code=status_code, detail=message_dict["message"]
                )

        @router.post("/storage/write_ipfs")
        async def storage_write_ipfs_endpoint(
            publish_to_ipns: bool = Form(False),
            update_ipns_name: Optional[str] = Form(None),
            file: UploadFile = File(...),
        ):
            """Write a file to IPFS, optionally publish to IPNS or update an existing IPNS record."""
            logger.info(f"Writing to IPFS: {file.filename}")
            logger.info(f"Publish to IPNS: {publish_to_ipns}")
            logger.info(f"Update IPNS name: {update_ipns_name}")
            status_code, message_dict = await write_to_ipfs(
                file, publish_to_ipns, update_ipns_name
            )
            logger.info(f"Status code: {status_code}")
            logger.info(f"Message dict: {message_dict}")

            if status_code == 201:
                return JSONResponse(status_code=status_code, content=message_dict)
            else:
                raise HTTPException(
                    status_code=status_code, detail=message_dict["message"]
                )

        @router.get("/storage/read_ipfs/{hash_or_name}")
        async def storage_read_ipfs_or_ipns_endpoint(hash_or_name: str):
            """Read a file from IPFS or IPNS."""
            status_code, message_dict = await read_from_ipfs_or_ipns(hash_or_name)
            if status_code == 200:
                if "content" in message_dict:
                    # For zipped directory content
                    return StreamingResponse(
                        io.BytesIO(message_dict["content"]),
                        media_type=message_dict["media_type"],
                        headers=message_dict["headers"],
                    )
                else:
                    # For single file content
                    return FileResponse(
                        path=message_dict["path"],
                        media_type=message_dict["media_type"],
                        filename=message_dict["filename"],
                        headers=message_dict["headers"],
                    )
            else:
                raise HTTPException(
                    status_code=status_code, detail=message_dict["message"]
                )

        # User endpoints
        @router.post("/user/check")
        async def user_check_endpoint(user_input: dict):
            """Check if a user exists."""
            _, response = await check_user(user_input)
            if '_sa_instance_state' in response:
                response.pop('_sa_instance_state')
            return response

        @router.post("/user/register")
        async def user_register_endpoint(user_input: dict):
            """Register a new user."""
            _, response = await register_user(user_input)
            if '_sa_instance_state' in response:
                response.pop('_sa_instance_state')
            return response

        # Monitor endpoints
        @router.post("/monitor/create_agent_run")
        async def monitor_create_agent_run_endpoint(
            agent_run_input: AgentRunInput,
        ) -> AgentRun:
            """Log a new agent run with orchestrator."""
            return await self.monitor_create_agent_run(agent_run_input)

        @router.post("/monitor/update_agent_run")
        async def monitor_update_agent_run_endpoint(agent_run: AgentRun) -> AgentRun:
            """Update an existing agent run with orchestrator."""
            return await self.monitor_update_agent_run(agent_run)

        # Include the router
        self.app.include_router(router)

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    async def agent_run(self, agent_run_input: AgentRunInput) -> AgentRun:
        """
        Run an agent
        :param agent_run_input: Agent run specifications
        :return: Status
        """
        try:
            logger.info(f"Received request to run an agent: {agent_run_input}")

            async with Hub() as hub:
                success, user, user_id = await hub.signin(
                    os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                )
                agent = await hub.list_agents(f"agent:{agent_run_input.agent_name}")
                logger.info(f"Found Agent: {agent}")

                if not agent:
                    raise HTTPException(status_code=404, detail="Agent not found")

                agent_run_input.agent_run_type = agent["type"]
                agent_run_input.agent_version = agent["version"]
                agent_run_input.agent_source_url = agent["url"]

                if agent_run_input.personas_urls is None:
                    if 'personas_urls' in agent:
                        agent_run_input.personas_urls = agent["personas_urls"]
                else:
                    if 'personas_urls' in agent:
                        agent_run_input.personas_urls.extend(agent["personas_urls"])

                if agent["type"] == "docker":
                    agent_run_input.agent_run_params = DockerParams(
                        **agent_run_input.agent_run_params
                    )

            async with DB() as db:
                agent_run = await db.create_agent_run(agent_run_input)
                logger.info("Created agent run")

            if agent_run:
                agent_run_data = agent_run.copy()
                agent_run_data.pop("_sa_instance_state", None)

            # Execute the task
            if agent_run['agent_run_type'] == "package":
                task = run_flow.delay(agent_run_data)
            elif agent_run['agent_run_type'] == "docker":
                task = execute_docker_agent.delay(agent_run_data)
            else:
                raise HTTPException(status_code=400, detail="Invalid agent run type")

            return agent_run_data

        except Exception as e:
            logger.error(f"Failed to run agent: {str(e)}")
            error_details = traceback.format_exc()
            logger.error(f"Full traceback: {error_details}")
            raise HTTPException(
                status_code=500, detail=f"Failed to run agent: {agent_run_input}"
            )

    async def agent_check(self, agent_run: AgentRun) -> AgentRun:
        """
        Check an agent
        :param agent_run: AgentRun details
        :return: Status
        """
        try:
            logger.info("Checking agent run")
            id_ = agent_run.id
            if id_ is None:
                raise HTTPException(status_code=400, detail="Agent run ID is required")

            async with DB() as db:
                agent_run = await db.list_agent_runs(id_)
                if isinstance(agent_run, list):
                    agent_run = agent_run[0]
                agent_run.pop("_sa_instance_state", None)
                if 'created_time' in agent_run and isinstance(agent_run['created_time'], datetime):
                    agent_run['created_time'] = agent_run['created_time'].isoformat()
                if 'start_processing_time' in agent_run and isinstance(agent_run['start_processing_time'], datetime):
                    agent_run['start_processing_time'] = agent_run['start_processing_time'].isoformat()
                if 'completed_time' in agent_run and isinstance(agent_run['completed_time'], datetime):
                    agent_run['completed_time'] = agent_run['completed_time'].isoformat()
                agent_run = AgentRun(**agent_run)

            if not agent_run:
                raise HTTPException(status_code=404, detail="Agent run not found")

            status = agent_run.status
            logger.info(f"Found agent status: {status}")

            if agent_run.status == "completed":
                logger.info(
                    f"Agent run completed. Returning output: {agent_run.results}"
                )
                response = agent_run.results
            elif agent_run.status == "error":
                logger.info(
                    f"Agent run failed. Returning error: {agent_run.error_message}"
                )
                response = agent_run.error_message
            else:
                response = None

            logger.info(f"Response: {response}")

            return agent_run

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to check agent run: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail="Internal server error occurred while checking agent run",
            )

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=0.5, max=10),
        retry=retry_if_exception_type(TransientDatabaseError),
        before_sleep=lambda retry_state: logger.info(
            f"Retrying operation, attempt {retry_state.attempt_number}"
        ),
    )
    async def monitor_create_agent_run(
        self, agent_run_input: AgentRunInput
    ) -> AgentRun:
        try:
            logger.info(
                f"Creating agent run for worker node {agent_run_input.worker_nodes[0]}"
            )
            async with DB() as db:
                agent_run = await db.create_agent_run(agent_run_input)
                if isinstance(agent_run, list):
                    agent_run = agent_run[0]
                agent_run.pop("_sa_instance_state", None)
                agent_run = AgentRun(**agent_run)
            logger.info(
                f"Created agent run for worker node {agent_run_input.worker_nodes[0]}"
            )
            return agent_run
        except Exception as e:
            logger.error(f"Failed to create agent run: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            if isinstance(e, asyncio.TimeoutError) or "Resource busy" in str(e):
                raise TransientDatabaseError(str(e))
            raise HTTPException(
                status_code=500,
                detail="Internal server error occurred while creating agent run",
            )

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=0.5, max=10),
        retry=retry_if_exception_type(TransientDatabaseError),
        before_sleep=lambda retry_state: logger.info(
            f"Retrying operation, attempt {retry_state.attempt_number}"
        ),
    )
    async def monitor_update_agent_run(self, agent_run: AgentRun) -> AgentRun:
        try:
            logger.info(
                f"Updating agent run for worker node {agent_run.worker_nodes[0]}"
            )
            async with DB() as db:
                updated_agent_run = await db.update_agent_run(agent_run.id, agent_run)
                if isinstance(updated_agent_run, list):
                    updated_agent_run = updated_agent_run[0]
                updated_agent_run.pop("_sa_instance_state", None)
                updated_agent_run = AgentRun(**updated_agent_run)
            logger.info(
                f"Updated agent run for worker node {agent_run.worker_nodes[0]}"
            )
            return updated_agent_run
        except Exception as e:
            logger.error(f"Failed to update agent run: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            if isinstance(e, asyncio.TimeoutError) or "Resource busy" in str(e):
                raise TransientDatabaseError(str(e))
            raise HTTPException(
                status_code=500,
                detail="Internal server error occurred while updating agent run",
            )

    async def launch_server(self):
        logger.info(f"Launching HTTP server on 0.0.0.0:{self.port}...")
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="debug",
            timeout_keep_alive=300,
            limit_concurrency=200,
            backlog=4096,
            reload=True,
        )
        server = uvicorn.Server(config)
        await server.serve()
