from fastapi import APIRouter, HTTPException, Body, Query, Path
from typing import Optional, Dict, Any, Union, List
import logging
import json
import io
import traceback
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse

from node.storage.storage_provider import (
    DatabaseStorageProvider,
    FilesystemStorageProvider,
    IPFSStorageProvider
)
from node.storage.schemas import StorageLocation, StorageType, DatabaseReadOptions
from node.storage.storage_provider import write_to_ipfs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage", tags=["storage"]) 
    
@router.post("/{storage_type}/create/{path:path}")
async def create_storage_object(
    storage_type: StorageType,
    path: str = Path(..., description="Storage path/identifier"),
    request_data: Dict[str, Any] = Body(..., description="Request data containing file content or database data")
):
    """Create new storage objects (table, file, or IPFS content)"""
    
    if storage_type == StorageType.DATABASE:
        storage_provider = DatabaseStorageProvider()
    elif storage_type == StorageType.FILESYSTEM:
        storage_provider = FilesystemStorageProvider()
    elif storage_type == StorageType.IPFS:
        storage_provider = IPFSStorageProvider()
    else:
        raise HTTPException(400, "Invalid storage type")

    location = StorageLocation(storage_type=storage_type, path=path)
    
    try:
        if storage_type == StorageType.DATABASE:
            return await storage_provider.create(location, request_data, {"type": "table"})
        elif storage_type == StorageType.FILESYSTEM:
            if "file" in request_data:
                return await storage_provider.create(location, request_data["file"], {"type": "file"})
            else:
                raise HTTPException(400, "Filesystem storage requires file upload")

        elif storage_type == StorageType.IPFS:
            """Write a file to IPFS, optionally publish to IPNS or update an existing IPNS record."""
            logger.info(f"Writing to IPFS: {request_data['file'].filename}")
            logger.info(f"Publish to IPNS: {request_data['publish_to_ipns']}")
            logger.info(f"Update IPNS name: {request_data['update_ipns_name']}")
            status_code, message_dict = await write_to_ipfs(
                request_data['file'], request_data['publish_to_ipns'], request_data['update_ipns_name']
            )
            logger.info(f"Status code: {status_code}")
            logger.info(f"Message dict: {message_dict}")

            if status_code == 201:
                return JSONResponse(status_code=status_code, content=message_dict)
            else:
                raise HTTPException(
                    status_code=status_code, detail=message_dict["message"]
                )


    except Exception as e:
        logger.error(f"Storage create error: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{storage_type}/read/{path:path}")
async def read_storage_object(
    storage_type: StorageType,
    path: str = Path(..., description="Storage path/identifier"),
    options: Optional[str] = Query(None, description="JSON string of options"),
):
    """Read from storage (query DB, read file, or fetch IPFS content)"""

    if storage_type == StorageType.DATABASE:
        storage_provider = DatabaseStorageProvider()
    elif storage_type == StorageType.FILESYSTEM:
        storage_provider = FilesystemStorageProvider()
    elif storage_type == StorageType.IPFS:
        storage_provider = IPFSStorageProvider()
    else:
        raise HTTPException(400, "Invalid storage type")

    location = StorageLocation(storage_type=storage_type, path=path)
    
    db_options = DatabaseReadOptions(**(json.loads(options) if options else {}))

    try:
        result = await storage_provider.read(location, db_options)

        # Handle different response types
        if storage_type == StorageType.DATABASE:
            return result.data
        elif storage_type == StorageType.FILESYSTEM:
            status_code, message_dict = await storage_provider.read(location, db_options)
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
        elif storage_type == StorageType.IPFS:
            return StreamingResponse(
                io.BytesIO(result.data),
                media_type=result.content_type
            )
            
    except Exception as e:
        logger.error(f"Storage read error: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{storage_type}/delete/{path:path}")
async def delete_storage_object(
    storage_type: StorageType,
    path: str = Path(..., description="Storage path/identifier"),
    condition: Optional[str] = Query(None, description="Delete condition for DB (JSON string)"),
    options: Optional[str] = Query(None, description="Storage-specific options (JSON string)")
):
    """Delete storage objects"""
    if storage_type == StorageType.DATABASE:
        storage_provider = DatabaseStorageProvider()
    elif storage_type == StorageType.FILESYSTEM:
        storage_provider = FilesystemStorageProvider()
    elif storage_type == StorageType.IPFS:
        storage_provider = IPFSStorageProvider()
    else:
        raise HTTPException(400, "Invalid storage type")

    location = StorageLocation(storage_type=storage_type, path=path)
    
    try:
        condition_dict = json.loads(condition) if condition else None
        options_dict = json.loads(options) if options else None

        if storage_type == StorageType.DATABASE and condition_dict:
            options_dict = {"condition": condition_dict, **(options_dict or {})}
        return await storage_provider.delete(storage_type, location, options_dict)
    
    except Exception as e:
        logger.error(f"Storage delete error: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{storage_type}/list/{path:path}")
async def list_storage_objects(
    storage_type: StorageType,
    path: str = Path(..., description="Storage path/identifier"),
    options: Optional[str] = Query(None, description="JSON string of options"),
):
    """List storage objects (DB tables/rows, directory contents, IPFS directory)"""

    if storage_type == StorageType.DATABASE:
        storage_provider = DatabaseStorageProvider()
    elif storage_type == StorageType.FILESYSTEM:
        storage_provider = FilesystemStorageProvider()
    elif storage_type == StorageType.IPFS:
        storage_provider = IPFSStorageProvider()
    else:
        raise HTTPException(400, "Invalid storage type")

    location = StorageLocation(storage_type=storage_type, path=path)
    
    db_options = DatabaseReadOptions(**(json.loads(options) if options else {}))

    try:
        return await storage_provider.list(location, db_options)
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/{storage_type}/search")
async def search_storage_objects(
    storage_type: StorageType,
    path: str = Body(..., description="Storage path/identifier"),
    query: Union[str, Dict[str, Any], List[float]] = Body(..., description="Search query"),
    query_type: Optional[str] = Body("text", description="Query type (text, vector, metadata)"),
    limit: Optional[int] = Query(None, description="Result limit"),
    options: Optional[Dict[str, Any]] = Body(None, description="Storage-specific options")
):
    """Search across storage (DB query, file content search, IPFS search)"""

    if storage_type == StorageType.DATABASE:
        storage_provider = DatabaseStorageProvider()
    elif storage_type == StorageType.FILESYSTEM:
        storage_provider = FilesystemStorageProvider()
    elif storage_type == StorageType.IPFS:
        storage_provider = IPFSStorageProvider()
    else:
        raise HTTPException(400, "Invalid storage type")


    location = StorageLocation(storage_type, path)
    
    try:
        search_options = {
            "query_type": query_type,
            "limit": limit,
            **(options or {})
        }
        return await storage_provider.search(location, query, search_options)
    except Exception as e:
        raise HTTPException(500, str(e))

