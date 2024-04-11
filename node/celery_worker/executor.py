import httpx
import asyncio
import subprocess

from node.utils import get_logger
from node.schemas import Job
from node.config import JOB_UPDATE_URL

logger = get_logger(__name__)


async def update_hub_with_status(job: Job):
    job_data = job.dict()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(JOB_UPDATE_URL, json=job_data)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"Failed to update hub with job status: {e}")
            raise e


async def execute_docker_job(job: Job):
    command = f"docker run {job.docker_image} {job.docker_command}"
    process = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    while True:
        # Check if process is complete
        if process.poll() is not None:
            if process.returncode == 0:
                job.status = "complete"
                job.reply = {"output": process.stdout.read().decode().strip()}
            else:
                job.status = "error"
                job.error = process.stderr.read().decode().strip()
            break

        # Update status to 'running'
        job.status = "running"
        job.reply = {"output": process.stdout.read().decode().strip()}

        logger.info(f"Updating job status: {job}")

        # Wait for 10 seconds before next update
        await asyncio.sleep(10)

    # Final update to the hub
    await update_hub_with_status(job)
