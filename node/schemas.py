from enum import Enum
from typing import Union
from datetime import datetime
from pydantic import BaseModel, Field


# Define enum for job types
class JobType(str, Enum):
    docker = "docker"
    template = "template"


class DockerJob(BaseModel):
    docker_image: str
    docker_command: str
    docker_num_gpus: int = 0
    docker_input_dir: Union[str, None] = None
    docker_output_dir: Union[str, None] = None
    docker_env_vars: Union[dict, None] = None

    class Config:
        allow_mutation = True


class JobInput(BaseModel):
    user_id: str
    module_id: str
    module_params: dict


class Job(BaseModel):
    # node_id: str
    job_type: JobType
    consumer: str
    module_id: str
    # id: Union[str, None] = None
    status: str = "pending"
    reply: Union[str, None] = None
    error: bool = False
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
    user_id: str
    address: str
    num_gpus: int
    vram: int
    os: str
    arch: str
    ram: int
    workflow_type: list[str]
    id: Union[str, None] = Field(default=None)
    token: str
    template_repo_tag: str

    class Config:
        allow_mutation = True


class JobId(BaseModel):
    id: str
