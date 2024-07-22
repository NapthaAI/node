import io
import json
from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from node.utils import get_logger, get_config
from node.comms.storage import write_to_ipfs, read_from_ipfs_or_ipns, write_storage, read_storage


logger = get_logger(__name__)


router = APIRouter()


BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]


@router.post("/write_storage")
async def write_storage_http(file: UploadFile = File(...)):
    """Write files to the storage."""
    status_code, message_dict = await write_storage(file)
    return JSONResponse(status_code=status_code, content=message_dict)


@router.get("/read_storage/{job_id}")
async def read_storage_http(job_id: str):
    """Get the output directory for a job_id and serve it as a tar.gz file."""
    status_code, message_dict = await read_storage(job_id)
    if status_code == 200:
        return FileResponse(
            path=message_dict["path"],
            media_type=message_dict["media_type"],
            filename=message_dict["filename"],
            headers=message_dict["headers"]
        )
    else:
        raise HTTPException(status_code=status_code, detail=message_dict["message"])


# class WriteToIPFSInput(BaseModel):
#     publish_to_ipns: bool = False
#     update_ipns_name: Optional[str] = None

#     @classmethod
#     def validate_to_json(cls, value):
#         if isinstance(value, str):
#             return cls(**json.loads(value))
#         return value

@router.post("/write_ipfs")
async def write_to_ipfs_http(
    publish_to_ipns: bool = Form(False),
    update_ipns_name: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    """Write a file to IPFS, optionally publish to IPNS or update an existing IPNS record."""
    logger.info(f"Writing to IPFS: {file.filename}")
    logger.info(f"Publish to IPNS: {publish_to_ipns}")
    logger.info(f"Update IPNS name: {update_ipns_name}")
    status_code, message_dict = await write_to_ipfs(file, publish_to_ipns, update_ipns_name)
    logger.info(f"Status code: {status_code}")
    logger.info(f"Message dict: {message_dict}")

    if status_code == 201:
        return JSONResponse(status_code=status_code, content=message_dict)
    else:
        raise HTTPException(status_code=status_code, detail=message_dict["message"])


@router.get("/read_ipfs/{hash_or_name}")
async def read_from_ipfs_or_ipns_http(hash_or_name: str):
    """Read a file from IPFS or IPNS."""
    status_code, message_dict = await read_from_ipfs_or_ipns(hash_or_name)
    if status_code == 200:
        if "content" in message_dict:
            # For zipped directory content
            return StreamingResponse(
                io.BytesIO(message_dict["content"]),
                media_type=message_dict["media_type"],
                headers=message_dict["headers"]
            )
        else:
            # For single file content
            return FileResponse(
                path=message_dict["path"],
                media_type=message_dict["media_type"],
                filename=message_dict["filename"],
                headers=message_dict["headers"]
            )
    else:
        raise HTTPException(status_code=status_code, detail=message_dict["message"])
