from fastapi import FastAPI, APIRouter, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
import uvicorn
import io
import os
import logging
import traceback
from datetime import datetime
from typing import Optional, Union
from node.schemas import (
    AgentRun,
    AgentRunInput,
    OrchestratorRun,
    OrchestratorRunInput,
    EnvironmentRun,
    EnvironmentRunInput,
)

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
from node.worker.template_worker import run_agent, run_environment, run_orchestrator
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
        self.server = None
        self.should_exit = False

        @self.app.on_event("shutdown")
        async def shutdown_event():
            logger.info("Received shutdown signal from FastAPI")
            self.should_exit = True
            # Add a short delay to allow the signal to propagate
            await asyncio.sleep(1)

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

        @router.post("/orchestrator/run")
        async def orchestrator_run_endpoint(orchestrator_run_input: OrchestratorRunInput) -> OrchestratorRun:
            """
            Run an agent orchestrator
            :param orchestrator_run_input: Orchestrator run specifications
            :return: Status
            """
            return await self.orchestrator_run(orchestrator_run_input)

        @router.post("/orchestrator/check")
        async def orchestrator_check_endpoint(orchestrator_run: OrchestratorRun) -> OrchestratorRun:
            """
            Check an orchestrator
            :param orchestrator_run: OrchestratorRun details
            :return: Status
            """
            return await self.orchestrator_check(orchestrator_run)

        @router.post("/environment/run")
        async def environment_run_endpoint(environment_run_input: EnvironmentRunInput) -> EnvironmentRun:
            """
            Run an environment
            :param environment_run_input: Environment run specifications 
            :return: Status
            """
            return await self.environment_run(environment_run_input)

        @router.post("/environment/check")
        async def environment_check_endpoint(environment_run: EnvironmentRun) -> EnvironmentRun:
            """
            Check an environment
            :param environment_run: EnvironmentRun details
            :return: Status
            """
            return await self.environment_check(environment_run)

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

    async def run_module(
        self, 
        run_input: Union[AgentRunInput, OrchestratorRunInput, EnvironmentRunInput]
    ) -> Union[AgentRun, OrchestratorRun, EnvironmentRun]:
        """
        Generic method to run either an agent, orchestrator, or environment
        :param run_input: Run specifications (AgentRunInput, OrchestratorRunInput, or EnvironmentRunInput)
        :return: Status
        """
        try:
            # Determine module type and configuration
            if isinstance(run_input, AgentRunInput):
                module_type = "agent"
                deployment = run_input.agent_deployment
                list_func = lambda hub: hub.list_agents(deployment.module['name'])
                create_func = lambda db: db.create_agent_run(run_input)
            elif isinstance(run_input, OrchestratorRunInput):
                module_type = "orchestrator"
                deployment = run_input.orchestrator_deployment
                list_func = lambda hub: hub.list_orchestrators(deployment.module['name'])
                create_func = lambda db: db.create_orchestrator_run(run_input)
            elif isinstance(run_input, EnvironmentRunInput):
                module_type = "environment"
                deployment = run_input.environment_deployment
                list_func = lambda hub: hub.list_environments(deployment.module['name'])
                create_func = lambda db: db.create_environment_run(run_input)
            else:
                raise HTTPException(status_code=400, detail="Invalid run input type")
                
            logger.info(f"Received request to run {module_type}: {run_input}")

            # Get module from hub
            async with Hub() as hub:
                _, _, _ = await hub.signin(
                    os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                )
                
                module = await list_func(hub)
                logger.info(f"Found {module_type.capitalize()}: {module}")

                if not module:
                    raise HTTPException(status_code=404, detail=f"{module_type.capitalize()} not found")

                # Update module info
                deployment.module = module

            # Create run record in DB
            async with DB() as db:
                run = await create_func(db)
                if not run:
                    raise HTTPException(status_code=500, detail=f"Failed to create {module_type} run")
                run_data = run.model_dump()

            # Execute the task based on module type
            if deployment.module.type == "package":
                if module_type == "agent":
                    _ = run_agent.delay(run_data)
                elif module_type == "orchestrator":
                    _ = run_orchestrator.delay(run_data)
                elif module_type == "environment":
                    _ = run_environment.delay(run_data)
            elif deployment.module.type == "docker" and module_type == "agent":
                _ = execute_docker_agent.delay(run_data)
            else:
                raise HTTPException(status_code=400, detail=f"Invalid {module_type} run type")

            return run_data

        except Exception as e:
            logger.error(f"Failed to run {module_type}: {str(e)}")
            error_details = traceback.format_exc()
            logger.error(f"Full traceback: {error_details}")
            raise HTTPException(
                status_code=500, detail=f"Failed to run {module_type}: {run_input}"
            )

    async def agent_run(self, agent_run_input: AgentRunInput) -> AgentRun:
        return await self.run_module(agent_run_input)

    async def orchestrator_run(self, orchestrator_run_input: OrchestratorRunInput) -> OrchestratorRun:
        return await self.run_module(orchestrator_run_input)

    async def environment_run(self, environment_run_input: EnvironmentRunInput) -> EnvironmentRun:
        return await self.run_module(environment_run_input)

    async def check_module(
        self, 
        module_run: Union[AgentRun, OrchestratorRun, EnvironmentRun]
    ) -> Union[AgentRun, OrchestratorRun, EnvironmentRun]:
        """
        Check a module run (agent, orchestrator, or environment)
        :param module_run: Run details (AgentRun, OrchestratorRun, or EnvironmentRun)
        :return: Status
        """
        try:
            # Determine module type and configuration
            if isinstance(module_run, AgentRun):
                module_type = "agent"
                list_func = lambda db: db.list_agent_runs(module_run.id)
            elif isinstance(module_run, OrchestratorRun):
                module_type = "orchestrator"
                list_func = lambda db: db.list_orchestrator_runs(module_run.id)
            elif isinstance(module_run, EnvironmentRun):
                module_type = "environment"
                list_func = lambda db: db.list_environment_runs(module_run.id)
            else:
                raise HTTPException(status_code=400, detail="Invalid module run type")

            logger.info(f"Checking {module_type} run")
            if module_run.id is None:
                raise HTTPException(status_code=400, detail=f"{module_type.capitalize()} run ID is required")

            async with DB() as db:
                run_data = await list_func(db)
                if isinstance(run_data, list):
                    run_data = run_data[0]
                run_data.pop("_sa_instance_state", None)
                
                # Convert datetime fields to ISO format
                for time_field in ['created_time', 'start_processing_time', 'completed_time']:
                    if time_field in run_data and isinstance(run_data[time_field], datetime):
                        run_data[time_field] = run_data[time_field].isoformat()
                
                # Convert back to appropriate type
                module_run = type(module_run)(**run_data)

            if not module_run:
                raise HTTPException(status_code=404, detail=f"{module_type.capitalize()} run not found")

            logger.info(f"Found {module_type} status: {module_run.status}")

            if module_run.status == "completed":
                logger.info(f"{module_type.capitalize()} run completed. Returning output: {module_run.results}")
                response = module_run.results
            elif module_run.status == "error":
                logger.info(f"{module_type.capitalize()} run failed. Returning error: {module_run.error_message}")
                response = module_run.error_message
            else:
                response = None

            logger.info(f"Response: {response}")
            return module_run

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to check {module_type} run: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            raise HTTPException(
                status_code=500,
                detail=f"Internal server error occurred while checking {module_type} run"
            )

    # Replace existing methods with wrappers that call check_module
    async def agent_check(self, agent_run: AgentRun) -> AgentRun:
        return await self.check_module(agent_run)

    async def orchestrator_check(self, orchestrator_run: OrchestratorRun) -> OrchestratorRun:
        return await self.check_module(orchestrator_run)

    async def environment_check(self, environment_run: EnvironmentRun) -> EnvironmentRun:
        return await self.check_module(environment_run)

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

    async def stop(self):
        """Handle graceful server shutdown"""
        if self.server and self._started:
            logger.info("Stopping HTTP server...")
            self.server.should_exit = True
            await self.server.shutdown()
            logger.info("HTTP server stopped")

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
            reload=False,  # Important: set to False for proper shutdown
            timeout_graceful_shutdown=30  # Add explicit graceful shutdown timeout
        )
        self.server = uvicorn.Server(config)
        self._started = True
        try:
            await self.server.serve()
        finally:
            self._started = False
