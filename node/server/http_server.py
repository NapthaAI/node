import asyncio
import io
import json
import httpx
import logging
import os
import traceback
from datetime import datetime
from typing import Optional, Union, Any, Dict

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, File, UploadFile, HTTPException, Form, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from node.config import MODULES_SOURCE_DIR
from node.module_manager import (
    install_module_with_lock, 
    load_agent_deployments, 
    load_tool_deployments, 
    load_orchestrator_deployments, 
    load_environment_deployments, 
    load_kb_deployments,
    load_deployments
)
from node.schemas import (
    AgentRun,
    AgentRunInput,
    ToolRun,
    ToolRunInput,
    OrchestratorRun,
    OrchestratorRunInput,
    EnvironmentRun,
    EnvironmentRunInput,
    DockerParams,
    ChatCompletionRequest,
    AgentDeployment, 
    OrchestratorDeployment, 
    EnvironmentDeployment,
    KBDeployment,
    KBRunInput,
    KBRun,
    AgentModuleType,
    ToolDeployment,
)
from node.storage.db.db import DB
from node.storage.hub.hub import Hub, list_modules
from node.storage.storage import (
    write_to_ipfs,
    read_from_ipfs_or_ipns,
    write_storage,
    read_storage,
)
from node.user import check_user, register_user
from node.config import LITELLM_URL
from node.worker.docker_worker import execute_docker_agent
from node.worker.template_worker import run_agent, run_tool, run_environment, run_orchestrator, run_kb

logger = logging.getLogger(__name__)
load_dotenv()

LITELLM_HTTP_TIMEOUT = 60*5

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
        
        @self.app.get("/health")
        async def health_check():
            return {"status": "ok", "server_type": "http"}
        
        # Handle validation errors when request data doesn't match the expected Pydantic models
        # Logs the validation error details and request body, then returns a 422 response with the error info
        @self.app.exception_handler(RequestValidationError)
        async def validation_exception_handler(request: Request, exc: RequestValidationError):
            logger.error(f"Request validation error: {exc.errors()}")
            logger.error(f"Request body: {await request.json()}")
            return JSONResponse(
                status_code=422,
                content={
                    "detail": exc.errors(),
                    "body": await request.json()
                }
            )

        @router.post("/agent/create")
        async def agent_create_endpoint(agent_input: AgentDeployment) -> AgentDeployment:
            """
            Create an agent
            :param agent_input: AgentDeployment
            :return: AgentDeployment
            """
            return await self.agent_create(agent_input)

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

        @router.post("/tool/create")
        async def tool_create_endpoint(tool_input: ToolDeployment) -> ToolDeployment:
            """
            Create a tool
            :param tool_input: ToolDeployment 
            :return: ToolDeployment
            """
            return await self.create_module(tool_input)

        @router.post("/tool/run")
        async def tool_run_endpoint(tool_run_input: ToolRunInput) -> ToolRun:
            """
            Run a tool
            :param tool_run_input: Tool run specifications
            :return: Status
            """
            return await self.tool_run(tool_run_input)

        @router.post("/tool/check")
        async def tool_check_endpoint(tool_run: ToolRun) -> ToolRun:
            """
            Check a tool
            :param tool_run: ToolRun details
            :return: Status
            """
            return await self.tool_check(tool_run)

        @router.post("/orchestrator/create")
        async def orchestrator_create_endpoint(orchestrator_input: OrchestratorDeployment) -> OrchestratorDeployment:
            """
            Create an agent orchestrator
            :param orchestrator_input: OrchestratorDeployment
            :return: OrchestratorDeployment
            """
            return await self.orchestrator_create(orchestrator_input)
        
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
        
        @router.post("/environment/create")
        async def environment_create_endpoint(environment_input: EnvironmentDeployment) -> EnvironmentDeployment:
            """
            Create an environment
            :param environment_input: EnvironmentDeployment
            :return: EnvironmentDeployment
            """
            return await self.environment_create(environment_input)

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

        @router.post("/kb/create")
        async def kb_create_endpoint(kb_input: KBDeployment) -> KBDeployment:
            """
            Create a knowledge base
            :param kb_input: KBDeployment
            :return: KBDeployment
            """
            return await self.kb_create(kb_input)
        
        @router.post("/kb/run")
        async def kb_run_endpoint(kb_run_input: KBRunInput) -> KBRun:
            """
            Run a knowledge base
            :param kb_run_input: KBRunInput
            :return: KBRun
            """
            return await self.kb_run(kb_run_input)

        @router.post("/kb/check")
        async def kb_check_endpoint(kb_run: KBRun) -> KBRun:
            """
            Check a knowledge base
            :param kb_run: KBRun details
            :return: Status
            """
            return await self.kb_check(kb_run)

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
        # Local DB endpoints
        @router.post("/local-db/create-table")
        async def create_local_table_endpoint(
            table_name: str = Body(...),
            schema: Dict[str, Dict[str, Any]] = Body(...)
        ) -> Dict[str, Any]:
            """Create a table in the local database"""
            logger.info(f"Creating table: {table_name} with schema: {schema}")
            return await self.create_local_table(table_name, schema)

        @router.post("/local-db/add-row")
        async def add_local_row_endpoint(
            table_name: str = Body(...),
            data: Dict[str, Any] = Body(...),
            schema: Optional[Dict[str, Dict[str, Any]]] = Body(None)
        ) -> Dict[str, Any]:
            """Add a row to a table in the local database"""
            return await self.add_local_row(table_name, data, schema)

        @router.post("/local-db/update-row")
        async def update_local_row_endpoint(
            table_name: str = Body(...),
            data: Dict[str, Any] = Body(...),
            condition: Dict[str, Any] = Body(...),
            schema: Optional[Dict[str, Dict[str, Any]]] = Body(None)  # Make schema optional
        ) -> Dict[str, Any]:
            """Update rows in a table in the local database"""
            return await self.update_local_row(table_name, data, condition, schema)

        @router.post("/local-db/delete-row")
        async def delete_local_row_endpoint(
            table_name: str = Body(...),
            condition: Dict[str, Any] = Body(...)
        ) -> Dict[str, Any]:
            """Delete rows from a table in the local database"""
            return await self.delete_local_row(table_name, condition)

        @router.get("/local-db/tables")
        async def list_tables_endpoint() -> Dict[str, Any]:
            """Get list of all tables in the local database"""
            return await self.list_local_tables()

        @router.get("/local-db/table/{table_name}")
        async def get_table_schema_endpoint(table_name: str) -> Dict[str, Any]:
            """Get schema information for a specific table"""
            return await self.get_local_table_schema(table_name)

        @router.get("/local-db/table/{table_name}/rows")
        async def query_table_rows_endpoint(
            table_name: str,
            columns: Optional[str] = None,
            condition: Optional[str] = None,
            order_by: Optional[str] = None,
            limit: Optional[int] = None
        ) -> Dict[str, Any]:
            """Query rows from a table with optional filters"""
            return await self.query_local_table(
                table_name, columns, condition, order_by, limit
            )

        @router.post("/local-db/vector_search")
        async def local_db_vector_search_endpoint(
            table_name: str = Body(...),
            vector_column: str = Body(...),
            query_vector: list[float] = Body(...),
            columns: Optional[list[str]] = Body(None),
            top_k: int = Body(5),
            include_similarity: bool = Body(True),
        ):
            return await self.local_db_vector_search(
                table_name,
                vector_column,
                query_vector,
                columns or ["text"],
                top_k,
                include_similarity,
            )

        ####### Inference endpoints #######
        @router.post("/inference/chat")
        async def chat_endpoint(request: ChatCompletionRequest):
            """
            Forward chat completion requests to litellm proxy
            """
            logger.info(f"Received chat request: {request}")
            try:
                async with httpx.AsyncClient(timeout=LITELLM_HTTP_TIMEOUT) as client:
                    response = await client.post(
                        f"{LITELLM_URL}/chat/completions",
                        json=request.model_dump(exclude_none=True)
                    )
                    logger.info(f"LiteLLM response: {response.json()}")
                    return response.json()
            except httpx.ReadTimeout:
                logger.error("Request to LiteLLM timed out")
                raise HTTPException(status_code=504, detail="Request to LiteLLM timed out")
            except Exception as e:
                logger.error(f"Error in chat endpoint: {str(e)}")
                logger.error(f"Full traceback: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail=str(e))

        # Include the router
        self.app.include_router(router)

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    async def create_module(self, module_deployment: Union[AgentDeployment, OrchestratorDeployment, EnvironmentDeployment, KBDeployment, ToolDeployment]) -> Dict[str, Any]:
        """
        Unified method to create and install any type of module and its sub-modules
        """
        try:
            # Determine module type and configuration
            if isinstance(module_deployment, AgentDeployment):
                module_type = "agent"
                module_name = module_deployment.module["name"] if isinstance(module_deployment.module, dict) else module_deployment.module.name
            elif isinstance(module_deployment, OrchestratorDeployment):
                module_type = "orchestrator"
                module_name = module_deployment.module["name"] if isinstance(module_deployment.module, dict) else module_deployment.module.name
            elif isinstance(module_deployment, EnvironmentDeployment):
                module_type = "environment"
                module_name = module_deployment.module["name"] if isinstance(module_deployment.module, dict) else module_deployment.module.name
            elif isinstance(module_deployment, KBDeployment):
                module_type = "kb"
                module_name = module_deployment.module["name"] if isinstance(module_deployment.module, dict) else module_deployment.module.name
            elif isinstance(module_deployment, ToolDeployment):
                module_type = "tool"
                module_name = module_deployment.module["name"] if isinstance(module_deployment.module, dict) else module_deployment.module.name
            else:
                raise HTTPException(status_code=400, detail="Invalid module deployment type")

            logger.info(f"Creating {module_type}: {module_deployment}")

            # Install main module
            module = await list_modules(module_type, module_name)
            if not module:
                raise HTTPException(status_code=404, detail=f"{module_type} {module_name} not found")

            try:
                await install_module_with_lock(module)
            except Exception as install_error:
                logger.error(f"Failed to install {module_type}: {str(install_error)}")
                logger.debug(f"Full traceback: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail=f"{module_type.capitalize()} installation failed: {str(install_error)}")

            # Set up paths for config files
            module_path = os.path.join(MODULES_SOURCE_DIR or "/tmp", module.name)
            config_path = os.path.join(module_path, module.name, "configs")

            deployment_status = {
                "status": "success",
                "message": f"{module_type.capitalize()} created successfully",
                "sub_modules": {}
            }

            # Load and process sub-deployments using specialized loaders
            loader_map = {
                "agent_deployments": (load_agent_deployments, "agent"),
                "tool_deployments": (load_tool_deployments, "tool"),
                "environment_deployments": (
                    lambda deployments, config_path: load_deployments(
                        deployments_path=config_path,  # Don't append filename here since it's already in config_path
                        input_deployments=deployments,
                        deployment_type="environment"
                    ),
                    "environment"
                ),
                "kb_deployments": (
                    lambda deployments, config_path: load_deployments(
                        deployments_path=config_path,  # Don't append filename here since it's already in config_path
                        input_deployments=deployments,
                        deployment_type="kb"
                    ),
                    "kb"
                )
            }

            for attr_name, (loader_func, sub_type) in loader_map.items():
                if hasattr(module_deployment, attr_name):
                    config_file = os.path.join(config_path, f"{attr_name}.json")
                    deployments = getattr(module_deployment, attr_name)

                    # Process if we have deployments in input OR config file exists
                    if deployments is not None or os.path.exists(config_file):
                        try:
                            # If no deployments passed but config exists, initialize empty list
                            if deployments is None and os.path.exists(config_file):
                                deployments = []

                            # Load and merge deployments
                            merged_deployments = await loader_func(deployments, config_file)
                            
                            # Install sub-modules
                            installation_status = []
                            sub_modules = set()
                            
                            for deployment in merged_deployments:
                                module_name = (deployment.module["name"] if isinstance(deployment.module, dict) 
                                            else deployment.module.name)
                                sub_modules.add(module_name)
                                
                                try:
                                    sub_module = await list_modules(sub_type, module_name)
                                    if sub_module:
                                        await install_module_with_lock(sub_module)
                                        installation_status.append({
                                            "name": module_name,
                                            "module_version": sub_module.module_version,
                                            "status": "success"
                                        })
                                except Exception as e:
                                    installation_status.append({
                                        "name": module_name,
                                        "module_version": "unknown",
                                        "status": str(e)
                                    })

                            deployment_status["sub_modules"][sub_type] = {
                                "modules": list(sub_modules),
                                "installation_status": installation_status
                            }
                            
                        except Exception as e:
                            logger.error(f"Failed to load {sub_type} deployments: {str(e)}")
                            logger.debug(f"Full traceback: {traceback.format_exc()}")

            return JSONResponse(content=deployment_status)

        except Exception as e:
            logger.error(f"Failed to create module: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))

    async def run_module(
        self, 
        run_input: Union[AgentRunInput, OrchestratorRunInput, EnvironmentRunInput, KBDeployment, ToolRunInput]
    ) -> Union[AgentRun, OrchestratorRun, EnvironmentRun, ToolRun]:
        """
        Generic method to run either an agent, orchestrator, environment, tool or kb
        :param run_input: Run specifications (AgentRunInput, OrchestratorRunInput, EnvironmentRunInput, ToolRunInput or KBRunInput)
        :return: Status
        """
        try:
            # Determine module type and configuration
            if isinstance(run_input, AgentRunInput):
                module_type = "agent"
                deployment = run_input.agent_deployment
                create_func = lambda db: db.create_agent_run(run_input)
            elif isinstance(run_input, ToolRunInput):
                module_type = "tool"
                deployment = run_input.tool_deployment
                create_func = lambda db: db.create_tool_run(run_input)
            elif isinstance(run_input, OrchestratorRunInput):
                module_type = "orchestrator"
                deployment = run_input.orchestrator_deployment
                create_func = lambda db: db.create_orchestrator_run(run_input)
            elif isinstance(run_input, EnvironmentRunInput):
                module_type = "environment"
                deployment = run_input.environment_deployment
                create_func = lambda db: db.create_environment_run(run_input)
            elif isinstance(run_input, KBRunInput):
                module_type = "kb"
                deployment = run_input.kb_deployment
                create_func = lambda db: db.create_kb_run(run_input)
            else:
                raise HTTPException(status_code=400, detail="Invalid run input type")
                
            logger.info(f"Received request to run {module_type}: {run_input}")

            deployment.module = await list_modules(module_type, deployment.module["name"])

            # Create run record in DB
            async with DB() as db:
                run = await create_func(db)
                if not run:
                    raise HTTPException(status_code=500, detail=f"Failed to create {module_type} run")
                run_data = run.model_dump()

                logger.info(f"Run data: {run_data}")

            # Execute the task based on module type
            if deployment.module.module_type == AgentModuleType.package:
                if module_type == "agent":
                    _ = run_agent.delay(run_data)
                elif module_type == "tool":
                    _ = run_tool.delay(run_data)
                elif module_type == "orchestrator":
                    _ = run_orchestrator.delay(run_data)
                elif module_type == "environment":
                    _ = run_environment.delay(run_data)
                elif module_type == "kb":
                    _ = run_kb.delay(run_data)
            elif deployment.module.module_type == AgentModuleType.docker and module_type == "agent":
                # validate docker params
                try:
                    _ = DockerParams(**run_data["inputs"])
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid docker params: {str(e)}")
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

    async def agent_create(self, agent_deployment: AgentDeployment) -> AgentDeployment:
        return await self.create_module(agent_deployment)

    async def tool_create(self, tool_deployment: ToolDeployment) -> ToolDeployment:
        return await self.create_module(tool_deployment)

    async def orchestrator_create(self, orchestrator_deployment: OrchestratorDeployment) -> OrchestratorDeployment:
        return await self.create_module(orchestrator_deployment)
    
    async def environment_create(self, environment_deployment: EnvironmentDeployment) -> EnvironmentDeployment:
        return await self.create_module(environment_deployment)

    async def kb_create(self, kb_deployment: KBDeployment) -> KBDeployment:
        return await self.create_module(kb_deployment)

    async def agent_run(self, agent_run_input: AgentRunInput) -> AgentRun:
        return await self.run_module(agent_run_input)

    async def tool_run(self, tool_run_input: ToolRunInput) -> ToolRun:
        return await self.run_module(tool_run_input)

    async def orchestrator_run(self, orchestrator_run_input: OrchestratorRunInput) -> OrchestratorRun:
        return await self.run_module(orchestrator_run_input)

    async def environment_run(self, environment_run_input: EnvironmentRunInput) -> EnvironmentRun:
        return await self.run_module(environment_run_input)

    async def kb_run(self, kb_run_input: KBRunInput) -> KBRun:
        return await self.run_module(kb_run_input)

    async def check_module(
        self, 
        module_run: Union[AgentRun, ToolRun, OrchestratorRun, EnvironmentRun]
    ) -> Union[AgentRun, ToolRun, OrchestratorRun, EnvironmentRun]:
        """
        Check a module run (agent, tool, orchestrator, or environment)
        :param module_run: Run details (AgentRun, ToolRun, OrchestratorRun, or EnvironmentRun)
        :return: Status
        """
        try:
            # Determine module type and configuration
            if isinstance(module_run, AgentRun):
                module_type = "agent"
                list_func = lambda db: db.list_agent_runs(module_run.id)
            elif isinstance(module_run, ToolRun):
                module_type = "tool"
                list_func = lambda db: db.list_tool_runs(module_run.id)
            elif isinstance(module_run, OrchestratorRun):
                module_type = "orchestrator"
                list_func = lambda db: db.list_orchestrator_runs(module_run.id)
            elif isinstance(module_run, EnvironmentRun):
                module_type = "environment"
                list_func = lambda db: db.list_environment_runs(module_run.id)
            elif isinstance(module_run, KBRun):
                module_type = "kb"
                list_func = lambda db: db.list_kb_runs(module_run.id)
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

                if 'results' in run_data and run_data['results']:
                    run_data['results'] = [r for r in run_data['results'] if r is not None]
    
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

    async def agent_check(self, agent_run: AgentRun) -> AgentRun:
        return await self.check_module(agent_run)

    async def tool_check(self, tool_run: ToolRun) -> ToolRun:
        return await self.check_module(tool_run)

    async def orchestrator_check(self, orchestrator_run: OrchestratorRun) -> OrchestratorRun:
        return await self.check_module(orchestrator_run)

    async def environment_check(self, environment_run: EnvironmentRun) -> EnvironmentRun:
        return await self.check_module(environment_run)

    async def kb_check(self, kb_run: KBRun) -> KBRun:
        return await self.check_module(kb_run)

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

    async def create_local_table(self, table_name: str, 
                            schema: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Create a table in the local database"""
        try:
            async with DB() as db:
                result = await db.create_dynamic_table(table_name, schema)
                return {"success": result, "message": f"Table {table_name} created successfully"}
        except Exception as e:
            logger.error(f"Failed to create table: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def add_local_row(self, table_name: str, data: Dict[str, Any], 
                        schema: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Add a row to the local database"""
        try:
            async with DB() as db:
                result = await db.add_dynamic_row(table_name, data)
                return {"success": result, "message": "Row added successfully"}
        except Exception as e:
            logger.error(f"Failed to add row: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def update_local_row(
        self, 
        table_name: str, 
        data: Dict[str, Any],
        condition: Dict[str, Any], 
        schema: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Update rows in the local database"""
        try:
            async with DB() as db:
                rows_updated = await db.update_dynamic_row(table_name, data, condition)
                return {"success": True, "rows_updated": rows_updated}
        except Exception as e:
            logger.error(f"Failed to update row: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_local_row(self, table_name: str, 
                            condition: Dict[str, Any]) -> Dict[str, Any]:
        """Delete rows from the local database"""
        try:
            async with DB() as db:
                rows_deleted = await db.delete_dynamic_row(table_name, condition)
                return {"success": True, "rows_deleted": rows_deleted}
        except Exception as e:
            logger.error(f"Failed to delete row: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def list_local_tables(self) -> Dict[str, Any]:
        """Get list of all tables"""
        try:
            async with DB() as db:
                tables = await db.list_dynamic_tables()
                return {"success": True, "tables": tables}
        except Exception as e:
            logger.error(f"Failed to list tables: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def get_local_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Get schema for a specific table"""
        try:
            async with DB() as db:
                schema = await db.get_dynamic_table_schema(table_name)
                return {"success": True, "table_name": table_name, "schema": schema}
        except Exception as e:
            logger.error(f"Failed to get table schema: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def query_local_table(self, table_name: str, 
                            columns: Optional[str] = None,
                            condition: Optional[str] = None, 
                            order_by: Optional[str] = None,
                            limit: Optional[int] = None) -> Dict[str, Any]:
        """Query rows from a table"""
        try:
            column_list = columns.split(',') if columns else None
            condition_dict = json.loads(condition) if condition else None
            
            async with DB() as db:
                rows = await db.query_dynamic_table(
                    table_name=table_name,
                    columns=column_list,
                    condition=condition_dict,
                    order_by=order_by,
                    limit=limit
                )
                return {"success": True, "rows": rows}
        except Exception as e:
            logger.error(f"Failed to query table: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    async def local_db_vector_search(
        self,
        table_name: str,
        vector_column: str,
        query_vector: list[float],
        columns: list[str],
        top_k: int,
        include_similarity: bool,
    ) -> Dict[str, Any]:
        async with DB() as db:
            results = await db.vector_similarity_search(
                table_name=table_name,
                vector_column=vector_column,
                query_vector=query_vector,
                columns=columns,
                top_k=top_k,
                include_similarity=include_similarity,
            )
        return {"success": True, "results": results}
        
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

    ###### toolset stuff ###############
    async def get_toolset_list(self, agent_run_id: str):
        pass
        
    ######### end toolset stuff ########