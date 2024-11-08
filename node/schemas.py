from enum import Enum
from typing import Dict, List, Optional, Union
from datetime import datetime
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


class AgentRunType(str, Enum):
    package = "package"
    docker = "docker"


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
    agent_name: str
    agent_run_type: AgentRunType
    consumer_id: str
    status: str = "pending"
    error: bool = False
    id: Optional[str] = None
    results: list[str] = []
    agent_personas: Optional[str] = None
    worker_nodes: Optional[list[str]] = None
    error_message: Optional[str] = None
    created_time: Optional[str] = None
    start_processing_time: Optional[str] = None
    completed_time: Optional[str] = None
    duration: Optional[float] = None
    agent_run_params: Optional[Union[Dict, DockerParams]] = None
    child_runs: List["AgentRun"] = []
    parent_runs: List["AgentRun"] = []
    input_schema_ipfs_hash: Optional[str] = None
    agent_source_url: Optional[str] = None
    agent_version: Optional[str] = None

    class Config:
        allow_mutation = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

    def model_dict(self):
        def convert_value(v):
            if isinstance(v, datetime):
                return v.isoformat()
            elif isinstance(v, AgentRunType):
                return v.value
            elif isinstance(v, BaseModel):
                return v.model_dict() if hasattr(v, "model_dict") else v.dict()
            elif isinstance(v, list):
                return [convert_value(item) for item in v]
            elif isinstance(v, dict):
                return {k: convert_value(val) for k, val in v.items()}
            else:
                return v

        return {k: convert_value(v) for k, v in self.dict(exclude_none=True).items()}


class AgentRunInput(BaseModel):
    agent_name: str
    consumer_id: str
    agent_personas: Optional[str] = None
    worker_nodes: Optional[list[str]] = None
    agent_run_params: Optional[Union[Dict, DockerParams]] = None
    agent_run_type: Optional[AgentRunType] = None
    parent_runs: List["AgentRun"] = []
    agent_source_url: Optional[str] = None
    agent_version: Optional[str] = None

    def model_dict(self):
        model_dict = self.dict()
        for i, parent_run in enumerate(model_dict["parent_runs"]):
            for key, value in parent_run.items():
                if isinstance(value, datetime):
                    model_dict["parent_runs"][i][key] = value.isoformat()
        return model_dict
