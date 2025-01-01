from enum import Enum
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field

class StorageType(str, Enum):
    DATABASE = "db"
    FILESYSTEM = "fs"
    IPFS = "ipfs"

class StorageLocation(BaseModel):
    storage_type: StorageType
    path: str
    options: Dict[str, Any] = Field(default_factory=dict)

    @property
    def uri(self) -> str:
        """Get URI representation of location"""
        return f"{self.storage_type.value}://{self.path}"
    
    @classmethod
    def from_uri(cls, uri: str) -> "StorageLocation":
        """Create StorageLocation from URI string"""
        scheme, path = uri.split("://", 1)
        return cls(storage_type=StorageType(scheme), path=path)

class StorageMetadata(BaseModel):
    content_type: Optional[str] = None
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    size: Optional[int] = None
    checksum: Optional[str] = None
    tags: Dict[str, str] = Field(default_factory=dict)
    custom: Dict[str, Any] = Field(default_factory=dict)

class StorageObject(BaseModel):
    location: StorageLocation
    data: Optional[Any] = None
    metadata: StorageMetadata = Field(default_factory=StorageMetadata)

class DatabaseReadOptions(BaseModel):
    """Options specific to database reads"""
    columns: Optional[List[str]] = None
    conditions: Optional[List[Dict[str, Any]]] = None
    order_by: Optional[str] = None
    order_direction: Optional[str] = "asc"
    limit: Optional[int] = None
    offset: Optional[int] = None
    # Added fields for QA/vector search
    query_col: Optional[str] = None  # Column to search against
    answer_col: Optional[str] = None  # Column to return as answer
    vector_col: Optional[str] = None  # Column containing vectors
    top_k: Optional[int] = Field(default=5, ge=1)  # Number of results for vector search
    include_similarity: Optional[bool] = Field(default=True)  # Include similarity scores
