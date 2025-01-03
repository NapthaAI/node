from abc import ABC, abstractmethod
import os
from node.config import BASE_OUTPUT_DIR, IPFS_GATEWAY_URL
from uuid import uuid4
from pathlib import Path
import ipfshttpclient
import zipfile
import shutil
import requests
import tempfile
import logging
from typing import Any, Dict, Union, BinaryIO, List

from node.storage.db.db import DB
from node.storage.schemas import StorageLocation, StorageObject, StorageType, DatabaseReadOptions
from node.storage.utils import zip_dir, zip_directory, get_api_url

logger = logging.getLogger(__name__)


class StorageProvider(ABC):
    """Abstract base class for storage providers"""
    
    @abstractmethod
    async def create(
        self, 
        location: StorageLocation, 
        data: Union[Dict, bytes, BinaryIO],
        options: Dict[str, Any] = None
    ) -> StorageObject:
        """Create a new object in storage"""
        pass

    @abstractmethod
    async def read(
        self, 
        location: StorageLocation,
        options: Dict[str, Any] = None
    ) -> StorageObject:
        """Read an object from storage"""
        pass

    @abstractmethod
    async def update(
        self,
        location: StorageLocation,
        data: Union[Dict, bytes, BinaryIO],
        options: Dict[str, Any] = None
    ) -> StorageObject:
        """Update an existing object in storage"""
        pass

    @abstractmethod
    async def delete(
        self,
        location: StorageLocation,
        options: Dict[str, Any] = None
    ) -> bool:
        """Delete an object from storage"""
        pass

    @abstractmethod
    async def list(
        self,
        location: StorageLocation,
        options: Dict[str, Any] = None
    ) -> List[StorageObject]:
        """List objects in a location"""
        pass

    @abstractmethod
    async def search(
        self,
        location: StorageLocation,
        query: Any,
        options: Dict[str, Any] = None
    ) -> List[StorageObject]:
        """Search for objects"""
        pass

class DatabaseStorageProvider(StorageProvider):
    """Implementation for database storage"""

    async def create(self, location: StorageLocation, request_data: Dict, db_options: Dict[str, Any] = None) -> StorageObject:
        table_name = location.path.split('/')[0]
        async with DB() as db:
            if "schema" in request_data:  
                logger.info(f"Creating table {table_name} with schema {request_data['schema']}")
                return await db.create_dynamic_table(table_name, request_data["schema"])
            elif "data" in request_data:  
                logger.info(f"Adding row(s) to table {table_name} with data {request_data['data']}")
                result = await db.add_dynamic_row(table_name, request_data["data"])
            return StorageObject(location=location, data=result)

    async def read(self, location: StorageLocation, db_options: DatabaseReadOptions = None) -> StorageObject:
        table_name = location.path.split('/')[0]
        
        async with DB() as db:
            try:
                # Vector similarity search
                if db_options.vector_col:
                    result = await db.vector_similarity_search(
                        table_name,
                        vector_column=db_options.vector_col,
                        query_vector=db_options.query_vector,
                        columns=db_options.columns or ['*'],
                        top_k=db_options.top_k,
                        include_similarity=db_options.include_similarity
                    )
                # Regular query
                else:
                    result = await db.query_dynamic_table(
                        table_name,
                        columns=db_options.columns,
                        condition=db_options.conditions[0] if db_options.conditions else None,
                        order_by=db_options.order_by,
                        limit=db_options.limit
                    )

                return StorageObject(
                    location=location,
                    data=result,
                )

            except Exception as e:
                raise ValueError(f"Database read failed: {str(e)}")

    async def delete(self, storage_type: StorageType, location: StorageLocation, options: Dict[str, Any] = None) -> bool:
        table_name = location.path.split('/')[0]

        async with DB() as db:
            if options and "condition" in options:  
                logger.info(f"Deleting row(s) from table {table_name} with data {options['condition']}")
                result = await db.delete_dynamic_row(table_name, options["condition"])
            else:  
                logger.info(f"Deleting table {table_name}")
                result = await db.delete_dynamic_table(table_name)

            return StorageObject(location=location, data=result)
 
    async def list(self, location: StorageLocation, options: DatabaseReadOptions = None) -> List[StorageObject]:
        table_name = location.path.split('/')[0]
        async with DB() as db:
            result = await db.list_dynamic_rows(table_name, limit=options.get("limit"), offset=options.get("offset"))
            return StorageObject(location=location, data=result)

    async def search(self, location: StorageLocation, query: Any, options: Dict[str, Any] = None) -> List[StorageObject]:
        pass

    async def update(self, location: StorageLocation, data: Union[Dict, bytes, BinaryIO], options: Dict[str, Any] = None) -> StorageObject:
        pass

class FilesystemStorageProvider(StorageProvider):
    """Implementation for filesystem storage"""
    
    async def create(self, location: StorageLocation, data: Union[bytes, BinaryIO], options: Dict[str, Any] = None) -> StorageObject:
        options = options or {}
        filename = options.get('filename')
        
        # Generate unique folder name if path is not specified
        if not location.path or location.path == '.':
            folder_name = uuid4().hex
            path = Path(BASE_OUTPUT_DIR) / folder_name
        else:
            path = Path(location.path)
            
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle file-like objects with filenames (e.g., FastAPI UploadFile)
        if hasattr(data, 'filename'):
            filename = data.filename
            file_path = path / filename
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(data.file, buffer)
                
            # Extract if it's a zip file
            if filename.endswith('.zip'):
                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    zip_ref.extractall(path)
                os.remove(file_path)  # Remove the zip file after extraction
        else:
            # Handle raw bytes or file-like objects without filenames
            if isinstance(data, bytes):
                path.write_bytes(data)
            else:
                path.write_bytes(data.read())

        return StorageObject(
            location=StorageLocation(storage_type=StorageType.FILESYSTEM, path=str(path)),
            data={"message": "Files written to storage", "folder_id": path.name}
        )

    async def read(self, location: StorageLocation, options: Dict[str, Any] = None) -> StorageObject:
        path = Path(location.path)
        
        # Handle directory reads
        if path.is_dir():
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmpfile:
                zip_directory(path, tmpfile.name)
                tmpfile.close()
                
                return StorageObject(
                    location=location,
                    data={
                        "path": tmpfile.name,
                        "media_type": "application/zip",
                        "filename": f"{path.name}.zip",
                        "headers": {
                            "Content-Disposition": f"attachment; filename={path.name}.zip"
                        },
                    }
                )
        
        # Handle single file reads
        else:
            data = path.read_bytes()
            return StorageObject(location, data=data)
    

class IPFSStorageProvider(StorageProvider):
    """Implementation for IPFS storage"""
    
    async def create(self, location: StorageLocation, data: Union[bytes, BinaryIO], options: Dict[str, Any] = None) -> StorageObject:
        publish_to_ipns = options.get('publish_to_ipns', False)
        status_code, message_dict = await write_to_ipfs(data, publish_to_ipns)
        return StorageObject(location, data=message_dict)

    async def read(self, location: StorageLocation, options: Dict[str, Any] = None) -> StorageObject:
        hash_or_name = location.path.split('/')[-1]
        status_code, message_dict = await read_from_ipfs_or_ipns(hash_or_name)
        return StorageObject(location, data=message_dict.get('content'))

async def write_to_ipfs(file, publish_to_ipns=False, update_ipns_name=None):
    """Write a file to IPFS, optionally publish to IPNS or update an existing IPNS record."""
    try:
        logger.info(f"Writing file to IPFS: {file.filename}")
        if not IPFS_GATEWAY_URL:
            return (500, {"message": "IPFS_GATEWAY_URL not found in environment"})

        client = ipfshttpclient.connect(IPFS_GATEWAY_URL)
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmpfile:
            content = await file.read()
            tmpfile.write(content)
            tmpfile_name = tmpfile.name
        file.file.close()

        result = client.add(tmpfile_name)
        client.pin.add(result["Hash"])
        os.unlink(tmpfile_name)

        ipfs_hash = result["Hash"]
        response = {
            "message": "File written and pinned to IPFS",
            "ipfs_hash": ipfs_hash,
        }

        if publish_to_ipns:
            ipns_hash = publish_to_ipns_func(ipfs_hash)
            response["ipns_hash"] = ipns_hash
            response["message"] += " and published to IPNS"
        elif update_ipns_name:
            updated_ipns_hash = update_ipns_record(update_ipns_name, ipfs_hash)
            response["ipns_hash"] = updated_ipns_hash
            response["message"] += " and IPNS record updated"

        return (201, response)
    except Exception as e:
        logger.error(f"Error writing file to IPFS: {e}")
        return (500, {"message": f"Error writing file to IPFS: {e}"})


async def read_from_ipfs_or_ipns(hash_or_name: str):
    """Read a file from IPFS or IPNS."""
    try:
        logger.info(f"Reading from IPFS/IPNS: {hash_or_name}")
        if not IPFS_GATEWAY_URL:
            return (500, {"message": "IPFS_GATEWAY_URL not found in environment"})

        # If it's an IPNS name, resolve it to an IPFS hash
        if hash_or_name.startswith("k"):
            ipfs_hash = get_ipns_record(hash_or_name)
        else:
            ipfs_hash = hash_or_name

        client = ipfshttpclient.connect(IPFS_GATEWAY_URL)
        temp_dir = tempfile.mkdtemp()
        client.get(ipfs_hash, target=temp_dir)
        file_path = os.path.join(temp_dir, ipfs_hash)

        if os.path.isdir(file_path):
            zip_buffer = zip_dir(file_path)
            return (
                200,
                {
                    "content": zip_buffer.getvalue(),
                    "media_type": "application/zip",
                    "headers": {
                        "Content-Disposition": f"attachment; filename={ipfs_hash}.zip"
                    },
                },
            )
        else:
            return (
                200,
                {
                    "path": file_path,
                    "media_type": "application/octet-stream",
                    "filename": os.path.basename(file_path),
                    "headers": {
                        "Content-Disposition": f"attachment; filename={os.path.basename(file_path)}"
                    },
                },
            )
    except Exception as e:
        logger.error(f"Error reading from IPFS/IPNS: {e}")
        return (500, {"message": f"Error reading from IPFS/IPNS: {e}"})


def publish_to_ipns_func(ipfs_hash: str) -> str:
    api_url = get_api_url()
    params = {
        "arg": ipfs_hash,
        "lifetime": "876000h",
    }  # Set lifetime to infinity (100 years)
    ipns_pub = requests.post(f"{api_url}/name/publish", params=params)
    return ipns_pub.json()["Name"]


def get_ipns_record(ipns_name: str) -> str:
    api_url = get_api_url()
    params = {"arg": ipns_name}
    ipns_get = requests.post(f"{api_url}/name/resolve", params=params)
    return ipns_get.json()["Path"].split("/")[-1]


def update_ipns_record(ipns_name: str, ipfs_hash: str) -> str:
    api_url = get_api_url()
    params = {
        "arg": ipfs_hash,
        "key": ipns_name,
        "lifetime": "876000h",
    }  # Set lifetime to infinity (100 years)
    ipns_pub = requests.post(f"{api_url}/name/publish", params=params)
    return ipns_pub.json()["Name"]
