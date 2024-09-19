from typing import List, Union
from pydantic import BaseModel, Field

class NodeConfig(BaseModel):
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

    class Config:
        allow_mutation = True