from fastapi import APIRouter, HTTPException
from node.celery_worker.celery_worker import execute_docker_job, execute_template_job
from node.storage.hub.hub import Hub
from node.storage.db.db import DB
from node.schemas import Job, JobInput, DockerJob
from node.utils import get_logger, get_config
from typing import Dict

logger = get_logger(__name__)

router = APIRouter()

BASE_OUTPUT_DIR = get_config()["BASE_OUTPUT_DIR"]


# Endpoint to receive a task
@router.post("/CreateTask")
async def create_task(job_input: JobInput) -> Dict:
    """
    Create a Task
    :param job: Job details
    :return: Status
    """
    try:
        logger.info(f"Received task: {job_input}")

        hub = await Hub()
        module = await hub.list_modules(f"module:{job_input.module_id}")
        logger.info(f"Found module: {module}")

        if not module:
            raise HTTPException(status_code=404, detail="Module not found")

        job = dict(job_input)
        job["job_type"] = module["type"]
        job = Job(**job)

        db = await DB("buyer1", "buyer1pass")
        job = await db.create_job(job)
        job = job[0]
        logger.info(f"Created job: {job}")

        updated_job = await db.update_job(job["id"], job)
        logger.info(f"Updated job: {updated_job}")

        # Validate the job type
        if job["job_type"] not in ["template", "docker"]:
            raise HTTPException(status_code=400, detail="Invalid job type")

        # Enqueue the job in Celery
        if job["job_type"] == "template":
            execute_template_job.delay(job)

        elif job["job_type"] == "docker":
            execute_docker_job.delay(job)
        else:
            raise HTTPException(status_code=400, detail="Invalid job type")

        return job

    except Exception as e:
        logger.error(f"Failed to execute job: {job} - {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to execute job: {job}")


@router.post("/CheckTask")
async def check_task(job: Dict) -> Dict:
    """
    Check a task
    :param job: Job details
    :return: Status
    """
    # try:
    logger.info(f"Checking task: {job}")

    db = await DB("buyer1", "buyer1pass")
    job = await db.list_tasks(job["id"])

    logger.info(f"Found task: {job}")

    status = job["status"]
    logger.info(f"Found task status: {status}")

    response = None
    if job["status"] == "completed":
        logger.info(f"Task completed. Returning output: {job['reply']}")
        response = job["reply"]
        logger.info(f"Response: {response}")
    elif job["status"] == "error":
        logger.info(f"Task failed. Returning error: {job['error_message']}")
        response = job["error_message"]
        logger.info(f"Response: {response}")

    return job
