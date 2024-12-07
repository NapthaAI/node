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
from fastapi import FastAPI, APIRouter, File, UploadFile, HTTPException, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from node.config import MODULES_SOURCE_DIR
from node.module_manager import ensure_module_installation_with_lock
from node.schemas import (
    AgentRun,
    AgentRunInput,
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
    ToolsetList,
    ToolsetListRequest,
    ToolsetDetails,
    ToolDetails,
    ToolsetLoadRepoRequest,
    ToolsetRequest,
    SetToolsetRequest    
)
from node.storage.db.db import DB
from node.storage.hub.hub import Hub
from node.storage.storage import (
    write_to_ipfs,
    read_from_ipfs_or_ipns,
    write_storage,
    read_storage,
)
from node.user import check_user, register_user
from node.config import LITELLM_URL
from node.worker.docker_worker import execute_docker_agent
from node.worker.template_worker import run_agent, run_environment, run_orchestrator, run_kb


###### toolset stuff ###############
from node.libs.toolset_manager.toolset_manager import ToolsetManager
######### end toolset stuff ########

logger = logging.getLogger(__name__)
load_dotenv()

LITELLM_HTTP_TIMEOUT = 60*5

class TransientDatabaseError(Exception):
    pass


class HTTPServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

        self.toolset_manager = ToolsetManager()

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
            
        ##################### Tool Endpoints #########################################
        @router.post("/tool/get_toolset_list")
        async def get_toolset_list_endpoint(request: ToolsetListRequest) -> ToolsetList:
            """Get the list of available toolsets for a given agent run."""
            # TODO: isolate tool calls from the node, maybe make a server?            
            toolset_list = ToolsetList(toolsets=[])
            toolset_names = self.toolset_manager.get_toolset_names()

            
            for toolset_name in toolset_names:
                toolset = ToolsetDetails(
                    id=toolset_name, 
                    name=toolset_name, 
                    description="Toolset description", 
                    tools=[])
                toolset_list.toolsets.append(toolset)
            return toolset_list
        
        @router.post("/tool/add_tool_repo_to_toolset")
        async def add_tool_repo_endpoint(toolset_repo_request: ToolsetLoadRepoRequest):
            """Add tool repository to toolset."""
            await self.toolset_manager.create_or_add_function_toolset_from_github(toolset_repo_request.toolset_name, toolset_repo_request.repo_url)

        @router.post("/tool/set_toolset")
        async def set_toolset_endpoint(load_toolset_resquest: SetToolsetRequest) -> ToolsetDetails:
            """Sets a toolset."""
            self.toolset_manager.set_current_toolset(load_toolset_resquest.toolset_name)
            toolset = self.toolset_manager.get_current_toolset()
            return ToolsetDetails(
                id=toolset.toolset_name, 
                name=toolset.toolset_name, 
                description= toolset.get_function_list_text(), 
                tools=[])
        
        @router.post("/tool/get_current_toolset")
        async def get_tool_list_endpoint(tool_list_request: ToolsetRequest) -> ToolsetDetails:
            """Get the list of available tools for a given toolset."""
            toolset = self.toolset_manager.get_current_toolset()
            return ToolsetDetails(
                        id=toolset.toolset_name, 
                        name=toolset.toolset_name, 
                        description= toolset.get_function_list_text(), 
                        tools=[])
            

        @router.post("/tool/run_tool")
        async def run_tool_endpoint(tool_name: str, tool_input: dict):
            """Run a tool."""
            return {"tool_name": tool_name, "tool_input": tool_input}
        
        @router.post("/tool/query_toolsets")
        async def query_toolsets_endpoint(toolset_name: str):
            """Query toolsets."""
            return {"toolset_name": toolset_name}

        @router.post("/tool/query_tools")
        async def query_tools_endpoint(tool_name: str):
            """Query tools."""
            return {"tool_name": tool_name}
        
        
        
        # create tool context
        @router.post("/tool/create_toolset")
        async def create_tool_context_endpoint(tool_name: str, tool_input: dict):
            """Create tool context."""
            return {"tool_name": tool_name, "tool_input": tool_input}
        
        # add tool to context
        @router.post("/tool/add_tool_to_toolset")
        async def add_tool_to_context_endpoint(tool_name: str, tool_input: dict):
            """Add tool to context."""
            return {"tool_name": tool_name, "tool_input": tool_input}

        # Include the router
        self.app.include_router(router)

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    async def orchestrator_create(self, orchestrator_input: OrchestratorDeployment) -> OrchestratorDeployment:
        """
        Create an agent orchestrator
        :param orchestrator_input: OrchestratorDeployment
        :return: OrchestratorDeployment
        """
        try:
            logger.info(f"Creating orchestrator: {orchestrator_input}")

            hub_username = os.getenv("HUB_USERNAME")
            hub_password = os.getenv("HUB_PASSWORD")
            if not hub_username or not hub_password:
                raise HTTPException(status_code=400, detail="Missing Hub authentication credentials")

            async with Hub() as hub:
                try:
                        _, _, _ = await hub.signin(hub_username, hub_password)
                except Exception as auth_error:
                    raise HTTPException(status_code=401, detail=f"Authentication failed: {str(auth_error)}")


                if isinstance(orchestrator_input.module, dict):
                    module_name = orchestrator_input.module.get("name")
                else:
                    module_name = orchestrator_input.module.name
                
                orchestrator = await hub.list_orchestrators(module_name)
                if not orchestrator:
                    raise HTTPException(status_code=404,
                                        detail=f"Orchestrator {orchestrator_input.module.name} not found")

            install_params = {
                "name": orchestrator.name or "unknown",
                "module_url": orchestrator.module_url or "",
                "module_version": f"v{orchestrator.module_version}" if orchestrator.module_version else "v0",
                "module_type": orchestrator.module_type or "default",
            }

            try:
                await ensure_module_installation_with_lock(install_params, f"v{orchestrator.module_version or '0'}")
            except Exception as install_error:
                logger.error(f"Failed to install orchestrator: {str(install_error)}")
                logger.debug(f"Full traceback: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail=f"Orchestrator installation failed: {str(install_error)}")

            agent_deployments = orchestrator_input.agent_deployments
            environment_deployments = orchestrator_input.environment_deployments

            orchestrator_path = os.path.join(MODULES_SOURCE_DIR or "/tmp", orchestrator.name or "unknown")
            orchestrator_config_path = os.path.join(orchestrator_path, orchestrator.name or "unknown", "configs")

            if not agent_deployments:
                agent_deployment_path = os.path.join(orchestrator_config_path, "agent_deployments.json")
                try:
                    with open(agent_deployment_path, "r") as f:
                        agent_deployments = json.load(f)
                except FileNotFoundError:
                    agent_deployments = []
                except Exception as e:
                    logger.error(f"Failed to load agent deployments: {str(e)}")
                    agent_deployments = []

            if not environment_deployments:
                environment_deployment_path = os.path.join(orchestrator_config_path, "environment_deployments.json")
                try:
                    with open(environment_deployment_path, "r") as f:
                        environment_deployments = json.load(f)
                except FileNotFoundError:
                    environment_deployments = []
                except Exception as e:
                    logger.error(f"Failed to load environment deployments: {str(e)}")
                    environment_deployments = []

            if not agent_deployments and not environment_deployments:
                return JSONResponse(content={"status": "success", "message": "Orchestrator created successfully. No agent or environment deployments found."})

            sub_agents = set()
            for agent_deployment in agent_deployments:
                if isinstance(agent_deployment, dict):
                    module = agent_deployment.get("module", {})
                    if isinstance(module, dict):
                        sub_agents.add(module.get("name"))
                    else:
                        sub_agents.add(module.name)
                else:
                    module = agent_deployment.module
                    if isinstance(module, dict):
                        sub_agents.add(module.get("name"))
                    else:
                        sub_agents.add(module.name)

            sub_agents = list(sub_agents)
            if len(sub_agents) > 0:
                agent_modules = []
                async with Hub() as hub:
                    _, _, _ = await hub.signin(
                        os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                    )
                    for sub_agent in sub_agents:
                        agent_module = await hub.list_agents(sub_agent)
                        if agent_module:
                            agent_modules.append(agent_module)
            
                logger.info(f"Agent modules: {agent_modules}")

                sub_agent_installation_status = []
                for agent_module in agent_modules:
                    install_params = {
                        "name": agent_module.name,
                        "module_url": agent_module.module_url,
                        "module_version": f"v{agent_module.module_version}",
                        "module_type": agent_module.module_type,
                    }
                    try:
                        await ensure_module_installation_with_lock(install_params, f"v{agent_module.module_version}")
                        sub_agent_installation_status.append({
                            "name": agent_module.name,
                            "module_version": agent_module.module_version,
                            "status": "success",
                        })
                    except Exception as e:
                        sub_agent_installation_status.append({
                            "name": agent_module.name,
                            "module_version": agent_module.module_version,
                            "status": str(e),
                        })
            else:
                sub_agent_installation_status = []

            sub_environments = set()
            for environment_deployment in environment_deployments:
                if isinstance(environment_deployment, dict):
                    module = environment_deployment.get("module", {})
                    if isinstance(module, dict):
                        sub_environments.add(module.get("name"))
                    else:
                        sub_environments.add(module.name)
                else:
                    module = environment_deployment.module
                    if isinstance(module, dict):
                        sub_environments.add(module.get("name"))
                    else:
                        sub_environments.add(module.name)

            sub_environments = list(sub_environments)
            if len(sub_environments) > 0:
                environment_modules = []
                async with Hub() as hub:
                    _, _, _ = await hub.signin(
                        os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                    )
                    for sub_environment in sub_environments:
                        environment_module = await hub.list_environments(sub_environment)
                        if environment_module:
                            environment_modules.append(environment_module)

                environment_installation_status = []
                for environment_module in environment_modules:
                    install_params = {
                        "name": environment_module.name,
                        "module_url": environment_module.module_url,
                        "module_version": f"v{environment_module.module_version}",
                        "module_type": environment_module.module_type,
                    }

                try:
                    await ensure_module_installation_with_lock(install_params, f"v{environment_module.module_version}")
                    environment_installation_status.append({
                        "name": environment_module.name,
                        "module_version": environment_module.module_version,
                        "status": "success",
                    })
                except Exception as e:
                    environment_installation_status.append({
                        "name": environment_module.name,
                        "module_version": environment_module.module_version,
                        "status": str(e),
                    })
            else:
                environment_installation_status = []

            return JSONResponse(
                content={
                    "status": "success", 
                    "message": "Orchestrator created successfully", 
                    "sub_agents": sub_agents, 
                    "sub_environments": sub_environments, 
                    "sub_agent_installation_status": sub_agent_installation_status, 
                    "sub_environment_installation_status": environment_installation_status
                }
            )

        except Exception as e:
            logger.error(f"Failed to create orchestrator: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))

    async def environment_create(self, environment_input: EnvironmentDeployment) -> EnvironmentDeployment:
        """
        Create an environment
        :param environment_input: EnvironmentDeployment
        :return: EnvironmentDeployment
        """
        try:
            hub_username = os.getenv("HUB_USERNAME")
            hub_password = os.getenv("HUB_PASSWORD")
            if not hub_username or not hub_password:
                raise HTTPException(status_code=400, detail="Missing Hub authentication credentials")

            async with Hub() as hub:
                _, _, _ = await hub.signin(
                    os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                )
                environment = await hub.list_environments(environment_input.name)
                if not environment:
                    raise HTTPException(status_code=404, detail=f"Environment {environment_input.name} not found")
            
            install_params = {
                "name": environment.name,
                "module_url": environment.module_url,
                "module_version": f"v{environment.module_version}",
                "module_type": environment.module_type,
            }

            try:
                await ensure_module_installation_with_lock(install_params, f"v{environment.module_version}")
            except Exception as e:
                logger.error(f"Failed to install environment: {str(e)}")
                logger.debug(f"Full traceback: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail=str(e))

            return JSONResponse(content={"status": "success", "message": "Environment created successfully"})
            
        except Exception as e:
            logger.error(f"Failed to create environment: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))

    async def agent_create(self, agent_input: AgentDeployment) -> AgentDeployment:
        """
        Create an agent
        :param agent_input: AgentDeployment
        :return: AgentDeployment
        """
        try:
            hub_username = os.getenv("HUB_USERNAME")
            hub_password = os.getenv("HUB_PASSWORD")
            if not hub_username or not hub_password:
                raise HTTPException(status_code=400, detail="Missing Hub authentication credentials")

            async with Hub() as hub:
                _, _, _ = await hub.signin(
                    os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                )
                agent = await hub.list_agents(agent_input.name)
                if not agent:
                    raise HTTPException(status_code=404, detail=f"Agent {agent_input.name} not found")
            
            install_params = {
                "name": agent.name,
                "module_url": agent.module_url,
                "module_version": f"v{agent.module_version}",
                "module_type": agent.module_type,
            }

            try:
                await ensure_module_installation_with_lock(install_params, f"v{agent.module_version}")
            except Exception as e:
                logger.error(f"Failed to install agent: {str(e)}")
                logger.debug(f"Full traceback: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail=str(e))
            
            return JSONResponse(content={"status": "success", "message": "Agent created successfully"})
        
        except Exception as e:
            logger.error(f"Failed to create agent: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))

    async def kb_create(self, kb_input: KBDeployment) -> KBDeployment:
        """
        Create a knowledge base
        :param kb_input: KBDeployment
        :return: KBDeployment
        """
        try:
            hub_username = os.getenv("HUB_USERNAME")
            hub_password = os.getenv("HUB_PASSWORD")
            if not hub_username or not hub_password:
                raise HTTPException(status_code=400, detail="Missing Hub authentication credentials")

            async with Hub() as hub:
                _, _, _ = await hub.signin(
                    os.getenv("HUB_USERNAME"), os.getenv("HUB_PASSWORD")
                )
                kb = await hub.list_knowledge_bases(kb_input.module['name'])
                if not kb:
                    raise HTTPException(status_code=404, detail=f"Knowledge base {kb_input.module['name']} not found")

                install_params = {
                    "name": kb.name,
                    "module_url": kb.module_url,
                    "module_version": f"v{kb.module_version}",
                    "module_type": kb.module_type,
                }

                try:
                    await ensure_module_installation_with_lock(install_params, f"v{kb.module_version}")
                except Exception as e:
                    logger.error(f"Failed to install knowledge base: {str(e)}")
                    logger.debug(f"Full traceback: {traceback.format_exc()}")
                    raise HTTPException(status_code=500, detail=str(e))
                
            return JSONResponse(content={"status": "success", "message": "Knowledge base created successfully"})
    
        except Exception as e:
            logger.error(f"Failed to create knowledge base: {str(e)}")
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def run_module(
        self, 
        run_input: Union[AgentRunInput, OrchestratorRunInput, EnvironmentRunInput, KBDeployment]
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
            elif isinstance(run_input, KBRunInput):
                module_type = "kb"
                deployment = run_input.kb_deployment
                list_func = lambda hub: hub.list_knowledge_bases(deployment.module['name'])
                create_func = lambda db: db.create_kb_run(run_input)
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

                logger.info(f"Run data: {run_data}")

            # Execute the task based on module type
            if deployment.module.module_type == AgentModuleType.package:
                if module_type == "agent":
                    _ = run_agent.delay(run_data)
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

    async def agent_run(self, agent_run_input: AgentRunInput) -> AgentRun:
        return await self.run_module(agent_run_input)

    async def orchestrator_run(self, orchestrator_run_input: OrchestratorRunInput) -> OrchestratorRun:
        return await self.run_module(orchestrator_run_input)

    async def environment_run(self, environment_run_input: EnvironmentRunInput) -> EnvironmentRun:
        return await self.run_module(environment_run_input)

    async def kb_run(self, kb_run_input: KBRunInput) -> KBRun:
        return await self.run_module(kb_run_input)

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

    # Replace existing methods with wrappers that call check_module
    async def agent_check(self, agent_run: AgentRun) -> AgentRun:
        return await self.check_module(agent_run)

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