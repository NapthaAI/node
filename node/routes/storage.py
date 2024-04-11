from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse
import tempfile
from node.utils import get_logger, get_config
import tarfile
from typing import Generator, List
from uuid import uuid4
from pathlib import Path

logger = get_logger(__name__)

router = APIRouter()

BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]


# Endpoint to write a file or directory to storage
@router.post("/WriteStorage")
async def write_storage(files: List[UploadFile] = File(...)):
    """Write files to the storage."""
    logger.info(f"Received request to write files to storage: {files}")
    folder_name = uuid4().hex
    folder_path = Path(BASE_OUTPUT_DIR) / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    for file in files:
        # Create subdirectories if they don't exist
        file_path = folder_path / Path(file.filename)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        with file_path.open("wb") as buffer:
            buffer.write(file.file.read())
        file.file.close()

    return JSONResponse(
        status_code=201,
        content={"message": "Files written to storage", "folder_id": folder_name},
    )


# Endpoint to get the output directory for a job_id NOTE: this isnt working because of anyio dependency issue with aiflow and openai
# @router.get("/GetStorage/{job_id}", response_class=StreamingResponse)
# async def get_task_output(job_id: str) -> StreamingResponse:
#     """
#     Get the output directory for a job_id
#     :param job_id: Job ID
#     :return: Output directory as a streamed tar.gz file
#     """
#     logger.info(f"Received request for output dir for job: {job_id}")
#     if ":" in job_id:
#         job_id = job_id.split(":")[1]

#     output_path = Path(BASE_OUTPUT_DIR) / job_id
#     logger.info(f"Output directory: {output_path}")

#     if not output_path.exists():
#         logger.error(f"Output directory not found for job: {job_id}")
#         return Response(status_code=404, content="Output directory not found")

#     def stream_tarball() -> Generator[bytes, None, None]:
#         with io.BytesIO() as buffer:
#             with tarfile.open(fileobj=buffer, mode="w:gz") as tar:

#                 def add_to_tar(tar, path, arcname):
#                     if path.is_dir():
#                         for item in path.iterdir():
#                             add_to_tar(tar, item, arcname / item.name)
#                     else:
#                         with path.open("rb") as file:
#                             file_data = file.read()
#                             tarinfo = tarfile.TarInfo(name=str(arcname))
#                             tarinfo.size = len(file_data)
#                             tar.addfile(tarinfo, io.BytesIO(file_data))

#                 add_to_tar(tar, output_path, Path(job_id))

#             buffer.seek(0)
#             yield from buffer

#     headers = {"Content-Disposition": f"attachment; filename={job_id}.tar.gz"}
#     return StreamingResponse(
#         stream_tarball(),
#         media_type="application/octet-stream",
#         headers=headers,
#         status_code=200,
#     )


@router.get("/GetStorage/{job_id}")
async def get_task_output(job_id: str):
    """
    Get the output directory for a job_id and serve it as a tar.gz file.
    :param job_id: Job ID
    :return: Output directory as a tar.gz file
    """
    logger.info(f"Received request for output dir for job: {job_id}")
    if ":" in job_id:
        job_id = job_id.split(":")[1]

    output_path = Path(BASE_OUTPUT_DIR) / job_id
    logger.info(f"Output directory: {output_path}")

    if not output_path.exists():
        logger.error(f"Output directory not found for job: {job_id}")
        raise HTTPException(status_code=404, detail="Output directory not found")

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
        with tarfile.open(tmpfile.name, "w:gz") as tar:
            for item in output_path.iterdir():
                tar.add(item, arcname=item.name)

    return FileResponse(
        path=tmpfile.name,
        media_type="application/gzip",
        filename=f"{job_id}.tar.gz",
        headers={"Content-Disposition": f"attachment; filename={job_id}.tar.gz"},
    )
