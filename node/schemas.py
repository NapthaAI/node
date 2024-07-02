from typing import List, Union
from pydantic import BaseModel, Field

class NodeConfigSchema(BaseModel):
    public_key: str
    num_gpus: int
    vram: int
    os: str
    arch: str
    ram: int
    ollama_models: List[str]
    id: Union[str, None] = Field(default=None)
    ip: Union[str, None] = Field(default=None)
    port: Union[int, None] = Field(default=None)
    routing: Union[str, None] = Field(default=None)
    owner: Union[str, None] = Field(default=None)

    class Config:
        allow_mutation = True