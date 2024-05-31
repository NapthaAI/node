from enum import Enum
from typing import Union, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field


# Define enum for job types
class JobType(str, Enum):
    docker = "docker"
    template = "template"


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


class JobInput(BaseModel):
    consumer_id: str
    module_id: str
    coworkers: Optional[list[str]] = None
    module_params: Optional[Dict] = None
    docker_params: Optional[DockerJob] = None


class JobUpdate(BaseModel):
    job_type: JobType
    consumer_id: str
    module_id: str
    id: str
    status: str = "pending"
    reply: Union[str, None] = None
    error: bool = False
    coworkers: Optional[list[str]] = None
    error_message: Union[str, None] = None
    created_time: Union[str, None] = None
    start_processing_time: Union[datetime, None] = None
    completed_time: Union[datetime, None] = None
    docker_params: Union[DockerJob, None] = None
    module_params: Union[dict, None] = None

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

class Job(BaseModel):
    # node_id: str
    job_type: JobType
    consumer_id: str
    module_id: str
    # id: Union[str, None] = None
    status: str = "pending"
    reply: Union[str, None] = None
    error: bool = False
    coworkers: Optional[list[str]] = None
    error_message: Union[str, None] = None
    created_time: Union[str, None] = None
    start_processing_time: Union[datetime, None] = None
    completed_time: Union[datetime, None] = None
    docker_params: Union[DockerJob, None] = None
    module_params: Union[dict, None] = None

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


class JobId(BaseModel):
    id: str
