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
from io import BytesIO
from typing import Any, Dict, Union, BinaryIO, List

from node.storage.db.db import DB
from node.storage.schemas import StorageLocation, StorageObject, StorageType, DatabaseReadOptions, IPFSOptions, StorageMetadata
from node.storage.utils import zip_directory, get_api_url
from node.config import IPFS_GATEWAY_URL

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

    async def delete(self, location: StorageLocation, options: Dict[str, Any] = None) -> bool:
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
            result = await db.list_dynamic_rows(table_name, limit=options.limit, offset=options.offset)
            return StorageObject(location=location, data=result)

    async def search(self, location: StorageLocation, query: Any, options: Dict[str, Any] = None) -> List[StorageObject]:
        pass

    async def update(self, location: StorageLocation, data: Union[Dict, bytes, BinaryIO], options: Dict[str, Any] = None) -> StorageObject:
        pass

class FilesystemStorageProvider(StorageProvider):
    """Implementation for filesystem storage"""
    
    async def create(self, location: StorageLocation, data: Union[bytes, BinaryIO], options: Dict[str, Any] = None) -> StorageObject:
        options = options or {}
        
        # Generate unique folder name if path is not specified
        if not location.path or location.path == '.':
            folder_name = uuid4().hex
            path = Path(BASE_OUTPUT_DIR) / folder_name
        else:
            path = Path(BASE_OUTPUT_DIR) / location.path  # Changed this line

        # Ensure directory exists
        path.mkdir(parents=True, exist_ok=True)
        
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
        path = Path(BASE_OUTPUT_DIR) / location.path
        
        # Handle directory reads
        if path.is_dir():
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmpfile:
                zip_directory(path, tmpfile.name)
                tmpfile.close()
                
                return StorageObject(
                    location=location,  # Changed from positional to keyword arg
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
            return StorageObject(
                location=location,  # Changed from positional to keyword arg
                data=data
            )

    async def delete(self, location: StorageLocation, options: Dict[str, Any] = None) -> bool:
        """Delete a file or directory from filesystem storage
        
        Args:
            location: StorageLocation object containing the path to delete
            options: Optional dictionary that can contain:
                - recursive: bool (default False) - Whether to recursively delete directories
                - ignore_missing: bool (default False) - Don't raise error if path doesn't exist
        
        Returns:
            bool: True if deletion was successful
            
        Raises:
            FileNotFoundError: If path doesn't exist and ignore_missing is False
            PermissionError: If permission denied when trying to delete
            OSError: For other filesystem-related errors
        """
        try:
            options = options or {}
            recursive = options.get('recursive', False)
            ignore_missing = options.get('ignore_missing', False)
            
            path = Path(BASE_OUTPUT_DIR) / location.path

            if not path.exists():
                if ignore_missing:
                    return True
                raise FileNotFoundError(f"Path does not exist: {path}")

            if path.is_file():
                path.unlink()
            elif path.is_dir():
                if recursive:
                    shutil.rmtree(path)
                else:
                    # Only delete if directory is empty
                    try:
                        path.rmdir()
                    except OSError as e:
                        if "Directory not empty" in str(e):
                            raise ValueError("Directory not empty. Use recursive=True to delete non-empty directories")
                        raise
            
            return True

        except PermissionError:
            logger.error(f"Permission denied when trying to delete: {path}")
            raise
        except Exception as e:
            logger.error(f"Error deleting from filesystem: {str(e)}")
            raise

    async def list(self, location: StorageLocation, options: Dict[str, Any] = None) -> List[StorageObject]:
        """List contents of a directory in filesystem storage
        
        Args:
            location: StorageLocation containing the directory path
            options: Optional dictionary containing:
                - recursive: bool (default False) - List contents recursively
                - include_dirs: bool (default True) - Include directories in results
                - pattern: str (default None) - Filter files by glob pattern
        
        Returns:
            List[StorageObject]: List of storage objects representing the contents
            
        Raises:
            FileNotFoundError: If directory doesn't exist
            NotADirectoryError: If path is not a directory
        """
        try:
            options = options or {}
            recursive = options.get('recursive', False)
            include_dirs = options.get('include_dirs', True)
            pattern = options.get('pattern', None)
            
            path = Path(BASE_OUTPUT_DIR) / location.path
            
            if not path.exists():
                raise FileNotFoundError(f"Path does not exist: {path}")
            
            if not path.is_dir():
                raise NotADirectoryError(f"Path is not a directory: {path}")

            results = []
            
            if recursive:
                iterator = path.rglob(pattern) if pattern else path.rglob('*')
            else:
                iterator = path.glob(pattern) if pattern else path.glob('*')
                
            for item in iterator:
                if not include_dirs and item.is_dir():
                    continue
                    
                # Get relative path from base directory
                rel_path = str(item.relative_to(Path(BASE_OUTPUT_DIR)))
                
                # Create metadata
                metadata = StorageMetadata(
                    content_type="directory" if item.is_dir() else None,
                    created_at=str(item.stat().st_ctime),
                    modified_at=str(item.stat().st_mtime),
                    size=item.stat().st_size if item.is_file() else None
                )
                
                results.append(StorageObject(
                    location=StorageLocation(
                        storage_type=StorageType.FILESYSTEM,
                        path=rel_path
                    ),
                    metadata=metadata
                ))
                
            return results
            
        except Exception as e:
            logger.error(f"Error listing directory contents: {str(e)}")
            raise
    
    async def update(self, location: StorageLocation, data: Union[Dict, bytes, BinaryIO], options: Dict[str, Any] = None) -> StorageObject:
        """Update not implemented yet"""
        raise NotImplementedError("Update not implemented yet for filesystem storage")

    async def search(self, location: StorageLocation, query: Any, options: Dict[str, Any] = None) -> List[StorageObject]:
        """Search not implemented yet"""
        raise NotImplementedError("Search not implemented yet for filesystem storage")

class IPFSStorageProvider(StorageProvider):
    """Implementation for IPFS storage with enhanced functionality"""
    
    def __init__(self):
        self.gateway_url = IPFS_GATEWAY_URL
        if not self.gateway_url:
            raise ValueError("IPFS_GATEWAY_URL not found in environment")
        self.client = None

    async def _get_client(self):
        """Get or create IPFS client"""
        if not self.client:
            self.client = ipfshttpclient.connect(self.gateway_url)
        return self.client

    async def create(
        self, 
        location: StorageLocation, 
        data: Union[bytes, BinaryIO],
        options: Union[Dict[str, Any], IPFSOptions] = None
    ) -> StorageObject:
        """Create new IPFS object"""
        try:
            client = await self._get_client()
            
            # Convert dict to IPFSOptions if needed
            if isinstance(options, dict):
                options = IPFSOptions(**options)
            else:
                options = options or IPFSOptions()
            
            logger.info(f"Creating IPFS object with options: {options}")

            # Handle file data
            with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmpfile:
                if hasattr(data, 'file'):  # UploadFile
                    content = await data.read()
                    filename = data.filename
                elif isinstance(data, bytes):
                    content = data
                    filename = "file"
                else:
                    content = await data.read()
                    filename = getattr(data, 'name', 'file')
                
                tmpfile.write(content)
                tmpfile_name = tmpfile.name

            # Add to IPFS
            result = client.add(tmpfile_name)
            ipfs_hash = result["Hash"]
            client.pin.add(ipfs_hash)
            os.unlink(tmpfile_name)

            response = {
                "message": "File written and pinned to IPFS",
                "ipfs_hash": ipfs_hash,
                "filename": filename
            }

            # Handle IPNS operations
            if options.ipns_operation == "create":
                logger.info("Publishing new IPNS record...")
                ipns_hash = await self._publish_to_ipns(ipfs_hash)
                response["ipns_hash"] = ipns_hash
                response["message"] += " and published to IPNS"
            elif options.ipns_operation == "update" and options.ipns_name:
                logger.info(f"Updating IPNS record {options.ipns_name}...")
                ipns_hash = await self._update_ipns_record(options.ipns_name, ipfs_hash)
                response["ipns_hash"] = ipns_hash
                response["message"] += " and updated IPNS record"

            # Handle unpinning if requested
            if options.unpin_previous and options.previous_hash:
                logger.info(f"Unpinning previous hash {options.previous_hash}")
                client.pin.rm(options.previous_hash)
                response["message"] += " and unpinned previous content"

            return StorageObject(location=location, data=response)

        except Exception as e:
            logger.error(f"Error in IPFS create: {str(e)}")
            raise

    async def read(
        self, 
        location: StorageLocation, 
        options: Union[Dict[str, Any], IPFSOptions] = None
    ) -> StorageObject:
        """Read content from IPFS/IPNS"""

        if isinstance(options, dict):
            options = IPFSOptions(**options)
        else:
            options = options or IPFSOptions()

        try:
            client = await self._get_client()
            hash_or_name = location.path.split('/')[-1]
            if options.resolve_ipns:
                force_resolve = options.resolve_ipns
            else:
                force_resolve = False

            # Resolve IPNS if needed
            if hash_or_name.startswith("k") or force_resolve:
                ipfs_hash = await self._resolve_ipns_to_ipfs(hash_or_name)
            else:
                ipfs_hash = hash_or_name

            # Get content from IPFS
            temp_dir = tempfile.mkdtemp()
            client.get(ipfs_hash, target=temp_dir)
            file_path = os.path.join(temp_dir, ipfs_hash)

            if os.path.isdir(file_path):
                # Handle directory by creating zip
                zip_buffer = BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for root, _, files in os.walk(file_path):
                        for file in files:
                            full_path = os.path.join(root, file)
                            relative_path = os.path.relpath(full_path, file_path)
                            zf.write(full_path, relative_path)
                
                return StorageObject(
                    location=location,
                    data={
                        "content": zip_buffer.getvalue(),
                        "media_type": "application/zip",
                        "filename": f"{ipfs_hash}.zip",
                        "is_directory": True
                    }
                )
            else:
                # Handle single file
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                return StorageObject(
                    location=location,
                    data={
                        "content": content,
                        "media_type": "application/octet-stream",
                        "filename": os.path.basename(file_path),
                        "is_directory": False
                    }
                )

        except Exception as e:
            logger.error(f"Error reading from IPFS: {e}")
            raise
        finally:
            # Cleanup
            if 'temp_dir' in locals():
                import shutil
                shutil.rmtree(temp_dir)

    async def _publish_to_ipns(self, ipfs_hash: str) -> str:
        """Publish new IPNS record"""
        api_url = get_api_url()
        params = {
            "arg": ipfs_hash,
            "lifetime": "876000h",  # 100 years
        }
        response = requests.post(f"{api_url}/name/publish", params=params)
        response.raise_for_status()
        return response.json()["Name"]

    async def _update_ipns_record(self, ipns_name: str, ipfs_hash: str) -> str:
        """Update existing IPNS record"""
        api_url = get_api_url()
        params = {
            "arg": ipfs_hash,
            "key": ipns_name,
            "lifetime": "876000h",
        }
        response = requests.post(f"{api_url}/name/publish", params=params)
        response.raise_for_status()
        return response.json()["Name"]

    async def _resolve_ipns_to_ipfs(self, ipns_name: str) -> str:
        """Resolve IPNS name to IPFS hash"""
        api_url = get_api_url()
        params = {"arg": ipns_name}
        response = requests.post(f"{api_url}/name/resolve", params=params)
        response.raise_for_status()
        return response.json()["Path"].split("/")[-1]

    # Implement remaining abstract methods
    async def update(self, location: StorageLocation, data: Union[Dict, bytes, BinaryIO], options: Dict[str, Any] = None) -> StorageObject:
        raise NotImplementedError("Update not implemented yet for filesystem storage")

    async def delete(self, location: StorageLocation, options: Dict[str, Any] = None) -> bool:
        raise NotImplementedError("Delete not implemented yet for filesystem storage")

    async def list(self, location: StorageLocation, options: Dict[str, Any] = None) -> List[StorageObject]:
        raise NotImplementedError("List not implemented yet for filesystem storage")

    async def search(self, location: StorageLocation, query: Any, options: Dict[str, Any] = None) -> List[StorageObject]:
        raise NotImplementedError("Search not implemented yet for filesystem storage")
