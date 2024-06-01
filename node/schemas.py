from enum import Enum
from typing import Dict, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field


class ModuleType(str, Enum):
    docker = "docker"
    template = "template"
    flow = "flow"

class DockerJob(BaseModel):
    docker_image: str
    docker_command: Optional[str] = ""
    docker_num_gpus: Optional[int] = 0
    docker_env_vars: Optional[Dict] = None
    input_dir: Optional[str] = None
    input_ipfs_hash: Optional[str] = None
    docker_input_dir: Optional[str] = None
    docker_output_dir: Optional[str] = None
    save_location: Optional[str] = None

    class Config:
        allow_mutation = True

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

class ModuleRun(BaseModel):
    module_name: str
    module_type: ModuleType
    consumer_id: str
    status: str = "pending"
    error: bool = False
    id: Optional[str] = None
    results: list[str] = []
    worker_nodes: Optional[list[str]] = None
    error_message: Optional[str] = None
    created_time: Optional[str] = None
    start_processing_time: Optional[datetime] = None
    completed_time: Optional[datetime] = None
    duration: Optional[datetime] = None
    docker_params: Optional[DockerJob] = None
    module_params: Optional[dict] = None
    child_runs: Optional[List['ModuleRun']] = None
    parent_runs: Optional[List['ModuleRun']] = None

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

class ModuleRunInput(BaseModel):
    module_name: str
    consumer_id: str
    worker_nodes: Optional[list[str]] = None
    module_params: Optional[Dict] = None
    docker_params: Optional[DockerJob] = None
    module_type: Optional[ModuleType] = None
    parent_runs: Optional[List['ModuleRun']] = None

class NodeConfigSchema(BaseModel):
    public_key: str
    num_gpus: int
    vram: int
    os: str
    arch: str
    ram: int
    id: Union[str, None] = Field(default=None)
    ip: Union[str, None] = Field(default=None)
    port: Union[int, None] = Field(default=None)
    routing: Union[str, None] = Field(default=None)

    class Config:
        allow_mutation = True


