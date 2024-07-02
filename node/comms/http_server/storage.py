from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from node.utils import get_logger, get_config
from node.comms.storage import write_to_ipfs, read_from_ipfs, write_storage, read_storage


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


@router.post("/write_ipfs")
async def write_to_ipfs_http(file: UploadFile = File(...)):
    """Write a file to IPFS and pin it."""
    status_code, message_dict = await write_to_ipfs(file)

    if status_code == 201:
        return JSONResponse(status_code=status_code, content=message_dict)
    else:
        raise HTTPException(status_code=status_code, detail=message_dict["message"])


@router.get("/read_ipfs/{ipfs_hash}")
async def read_from_ipfs_http(ipfs_hash: str):
    """Read a file from IPFS."""
    status_code, message_dict = await read_from_ipfs(ipfs_hash)
    if status_code == 200:
        return FileResponse(
            path=message_dict["path"],
            media_type=message_dict["media_type"],
            filename=message_dict["filename"],
            headers=message_dict["headers"]
        )
    else:
        raise HTTPException(status_code=status_code, detail=message_dict["message"])
