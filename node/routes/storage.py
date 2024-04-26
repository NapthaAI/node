import os
import io
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from starlette.responses import Response
from node.utils import get_logger, get_config
import tarfile
from uuid import uuid4
from pathlib import Path
import ipfshttpclient
import zipfile
import shutil
import tempfile

logger = get_logger(__name__)

router = APIRouter()

BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]


def zip_dir(directory_path: str) -> io.BytesIO:
    """
    Zip the specified directory and return a BytesIO object containing the zip file.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                zip_file.write(file_path, os.path.relpath(file_path, directory_path))
    zip_buffer.seek(0)
    return zip_buffer


@router.post("/write_storage")
async def write_storage(file: UploadFile = File(...)):
    """Write files to the storage."""
    logger.info(f"Received request to write files to storage: {file.filename}")
    folder_name = uuid4().hex
    folder_path = Path(BASE_OUTPUT_DIR) / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    temp_file_path = folder_path / file.filename

    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if file.filename.endswith(".zip"):
        with zipfile.ZipFile(temp_file_path, "r") as zip_ref:
            zip_ref.extractall(folder_path)

        # delete zip file
        os.remove(temp_file_path)
    else:
        pass

    return JSONResponse(
        status_code=201,
        content={"message": "Files written to storage", "folder_id": folder_name},
    )

def zip_directory(file_path, zip_path):
    """Utility function to zip the content of a directory while preserving the folder structure."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(file_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=os.path.abspath(file_path).split(os.sep)[0])
                zipf.write(file_path, arcname)

@router.get("/read_storage/{job_id}")
async def read_storage(job_id: str):
    """Get the output directory for a job_id and serve it as a tar.gz file."""
    logger.info(f"Received request for output dir for job: {job_id}")
    if ":" in job_id:
        job_id = job_id.split(":")[1]

    job_id = job_id.strip()

    output_path = Path(BASE_OUTPUT_DIR) / job_id
    logger.info(f"Output directory: {output_path}")

    if not output_path.exists():
        logger.error(f"Output directory not found for job: {job_id}")
        raise HTTPException(status_code=404, detail="Output directory not found")

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmpfile:
        zip_directory(output_path, tmpfile.name)
        tmpfile.close()

        return FileResponse(
            path=tmpfile.name,
            media_type="application/zip",
            filename=f"{job_id}.zip",
            headers={"Content-Disposition": f"attachment; filename={job_id}.zip"}
        )


@router.post("/write_ipfs")
async def write_to_ipfs(file: UploadFile = File(...)):
    """Write a file to IPFS and pin it."""
    try:
        logger.info(f"Received request to write file to IPFS: {file.filename}")

        # Get IPFS_GATEWAY_URL from environment
        IPFS_GATEWAY_URL = os.getenv("IPFS_GATEWAY_URL", None)
        if not IPFS_GATEWAY_URL:
            logger.error("IPFS_GATEWAY_URL not found in environment")
            raise HTTPException(
                status_code=500, detail="IPFS_GATEWAY_URL not found in environment"
            )

        # Connect to IPFS node
        client = ipfshttpclient.connect(IPFS_GATEWAY_URL)

        # Create a temporary file to ensure compatibility with IPFS
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmpfile:
            content = await file.read()  # Read the content of the uploaded file
            tmpfile.write(content)
            tmpfile_name = tmpfile.name

        # Ensure the file is closed before adding it to IPFS
        file.file.close()

        # Add file to IPFS
        result = client.add(tmpfile_name)

        # Pin the file in IPFS to ensure persistence
        client.pin.add(result["Hash"])

        # Optionally, clean up the temporary file if desired
        os.unlink(tmpfile_name)

        # Result['Hash'] contains the IPFS hash of the uploaded file
        return JSONResponse(
            status_code=201,
            content={
                "message": "File written and pinned to IPFS",
                "ipfs_hash": result["Hash"],
            },
        )
    except Exception as e:
        logger.error(f"Error writing and pinning file to IPFS: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error writing and pinning file to IPFS: {e}"
        )


@router.get("/read_ipfs/{ipfs_hash}")
async def read_from_ipfs(ipfs_hash: str):
    """Read a file from IPFS."""
    try:
        logger.info(f"Received request to read file from IPFS: {ipfs_hash}")

        IPFS_GATEWAY_URL = os.getenv("IPFS_GATEWAY_URL", None)
        if not IPFS_GATEWAY_URL:
            logger.error("IPFS_GATEWAY_URL not found in environment")
            raise HTTPException(
                status_code=500, detail="IPFS_GATEWAY_URL not found in environment"
            )

        client = ipfshttpclient.connect(IPFS_GATEWAY_URL)

        # Specify the directory to save the downloaded files
        temp_dir = tempfile.mkdtemp()
        client.get(ipfs_hash, target=temp_dir)

        # Determine if the path is a file or directory
        file_path = os.path.join(temp_dir, ipfs_hash)
        if os.path.isdir(file_path):
            # It's a directory, zip it
            zip_buffer = zip_dir(file_path)
            return Response(
                content=zip_buffer.getvalue(),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f"attachment; filename={ipfs_hash}.zip"
                },
            )
        else:
            # It's a single file, stream it directly
            return FileResponse(
                path=file_path,
                media_type="application/octet-stream",
                filename=os.path.basename(file_path),
            )

    except Exception as e:
        logger.error(f"Error reading file from IPFS: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error reading file from IPFS: {e}"
        )
