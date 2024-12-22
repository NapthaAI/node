from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field


class NodeConfig(BaseModel):
    id: str
    public_key: str
    num_gpus: int
    vram: int
    os: str
    arch: str
    ram: int
    ollama_models: List[str]
    docker_jobs: bool
    ip: Union[str, None] = Field(default=None)
    ports: List[int] = Field(default_factory=list)
    routing: Union[str, None] = Field(default=None)
    owner: Union[str, None] = Field(default=None)
    num_servers: int = Field(default=1)
    node_type: str = Field(default="direct")
    server_type: str = Field(default="http")

    class Config:
        allow_mutation = True

class LLMClientType(str, Enum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    VLLM = "vllm"
    LITELLM = "litellm"
    OLLAMA = "ollama"

class LLMConfig(BaseModel):
    config_name: Optional[str] = None
    client: Optional[LLMClientType] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    api_base: Optional[str] = None

class AgentModuleType(str, Enum):
    package = "package"
    docker = "docker"

class AgentModule(BaseModel):
    id: str
    name: str
    description: str
    author: str
    module_url: str
    module_type: Optional[AgentModuleType] = AgentModuleType.package
    module_version: Optional[str] = "0.1"
    module_entrypoint: Optional[str] = "run.py"
    personas_urls: Optional[List[str]] = None

class AgentConfig(BaseModel):
    config_name: Optional[str] = None
    llm_config: Optional[LLMConfig] = None
    persona_module: Optional[Union[Dict, BaseModel]] = None
    system_prompt: Optional[Union[Dict, BaseModel]] = None

class OrchestratorConfig(BaseModel):
    config_name: Optional[str] = "orchestrator_config"
    max_rounds: Optional[int] = 5

class EnvironmentConfig(BaseModel):
    config_name: Optional[str] = None
    environment_type: Optional[str] = None

class DataGenerationConfig(BaseModel):
    save_outputs: Optional[bool] = None
    save_outputs_location: Optional[str] = None
    save_outputs_path: Optional[str] = None
    save_inputs: Optional[bool] = None
    save_inputs_location: Optional[str] = None

class KBDeployment(BaseModel):
    name: Optional[str] = "kb_deployment"
    module: Optional[Union[Dict, AgentModule]] = None
    kb_node_url: Optional[str] = "http://localhost:7001"
    kb_config: Optional[Dict] = None

class AgentDeployment(BaseModel):
    name: Optional[str] = "agent_deployment"
    module: Optional[Union[Dict, AgentModule]] = None
    worker_node_url: Optional[str] = None
    agent_config: Optional[AgentConfig] = AgentConfig()
    data_generation_config: Optional[DataGenerationConfig] = DataGenerationConfig()
    kb_deployments: Optional[List[KBDeployment]] = None

class EnvironmentDeployment(BaseModel):
    name: Optional[str] = "environment_deployment"
    module: Optional[Union[Dict, AgentModule]] = None
    environment_node_url: str
    environment_config: Optional[Union[Dict, BaseModel]] = EnvironmentConfig()

class OrchestratorDeployment(BaseModel):
    name: Optional[str] = "orchestrator_deployment"
    module: Optional[Union[Dict, AgentModule]] = None
    orchestrator_node_url: Optional[str] = "http://localhost:7001"
    orchestrator_config: Optional[OrchestratorConfig] = OrchestratorConfig()
    environment_deployments: Optional[List[EnvironmentDeployment]] = None
    agent_deployments: Optional[List[AgentDeployment]] = None

class DockerParams(BaseModel):
    docker_image: str
    docker_command: Optional[str] = ""
    docker_num_gpus: Optional[int] = 0
    docker_env_vars: Optional[Dict] = None
    input_dir: Optional[str] = None
    input_ipfs_hash: Optional[str] = None
    docker_input_dir: Optional[str] = None
    docker_output_dir: Optional[str] = None
    save_location: str = "node"

    class Config:
        allow_mutation = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

    def model_dict(self):
        model_dict = self.dict()
        for key, value in model_dict.items():
            if isinstance(value, datetime):
                model_dict[key] = value.isoformat()
        return model_dict


class AgentRun(BaseModel):
    consumer_id: str
    inputs: Optional[Union[Dict, BaseModel, DockerParams]] = None
    agent_deployment: AgentDeployment
    orchestrator_runs: List['OrchestratorRun'] = []
    status: str = "pending"
    error: bool = False
    id: Optional[str] = None
    results: list[str] = []
    error_message: Optional[str] = None
    created_time: Optional[str] = None
    start_processing_time: Optional[str] = None
    completed_time: Optional[str] = None
    duration: Optional[float] = None
    input_schema_ipfs_hash: Optional[str] = None

    class Config:
        allow_mutation = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

    def model_dict(self):
        model_dict = self.dict()
        for key, value in model_dict.items():
            if isinstance(value, datetime):
                model_dict[key] = value.isoformat()
            elif isinstance(value, AgentModuleType):
                model_dict[key] = value.value
        for i, orchestrator_run in enumerate(model_dict['orchestrator_runs']):
            for key, value in orchestrator_run.items():
                if isinstance(value, datetime):
                    model_dict['orchestrator_runs'][i][key] = value.isoformat()
        return model_dict


class AgentRunInput(BaseModel):
    consumer_id: str
    inputs: Optional[Union[Dict, BaseModel, DockerParams]] = None
    agent_deployment: AgentDeployment = AgentDeployment()
    orchestrator_runs: List['OrchestratorRun'] = []
    
class OrchestratorRunInput(BaseModel):
    consumer_id: str
    inputs: Optional[Union[Dict, BaseModel, DockerParams]] = None
    orchestrator_deployment: OrchestratorDeployment

class OrchestratorRun(BaseModel):
    consumer_id: str
    inputs: Optional[Union[Dict, BaseModel, DockerParams]] = None
    orchestrator_deployment: OrchestratorDeployment
    status: str = "pending"
    error: bool = False
    id: Optional[str] = None
    results: list[str] = []
    error_message: Optional[str] = None
    created_time: Optional[str] = None
    start_processing_time: Optional[str] = None
    completed_time: Optional[str] = None
    duration: Optional[float] = None
    agent_runs: List['AgentRun'] = []
    input_schema_ipfs_hash: Optional[str] = None

class EnvironmentRunInput(BaseModel):
    consumer_id: str
    inputs: Optional[Union[Dict, BaseModel, DockerParams]] = None
    environment_deployment: EnvironmentDeployment
    orchestrator_runs: List['OrchestratorRun'] = []

class EnvironmentRun(BaseModel):
    consumer_id: str
    inputs: Optional[Union[Dict, BaseModel, DockerParams]] = None
    environment_deployment: EnvironmentDeployment
    orchestrator_runs: List['OrchestratorRun'] = []
    status: str = "pending"
    error: bool = False
    id: Optional[str] = None
    results: list[str] = []
    error_message: Optional[str] = None
    created_time: Optional[str] = None
    start_processing_time: Optional[str] = None
    completed_time: Optional[str] = None
    duration: Optional[float] = None
    input_schema_ipfs_hash: Optional[str] = None

class KBRunInput(BaseModel):
    consumer_id: str
    inputs: Optional[Union[Dict, BaseModel, DockerParams]] = None
    kb_deployment: KBDeployment
    orchestrator_runs: List['OrchestratorRun'] = []

class KBRun(BaseModel):
    consumer_id: str
    inputs: Optional[Union[Dict, BaseModel, DockerParams]] = None
    kb_deployment: KBDeployment
    orchestrator_runs: List['OrchestratorRun'] = []
    status: str = "pending"
    error: bool = False
    id: Optional[str] = None
    results: list[Optional[str]] = []   
    error_message: Optional[str] = None
    created_time: Optional[str] = None
    start_processing_time: Optional[str] = None
    completed_time: Optional[str] = None
    duration: Optional[float] = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[List[str]] = None
    stream: Optional[bool] = None
