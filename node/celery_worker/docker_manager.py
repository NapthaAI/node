import os
import asyncio
import time
from typing import Dict, Optional
from datetime import datetime
import pytz
import docker
from docker.types import DeviceRequest
from docker.models.containers import Container
from docker.errors import ContainerError, ImageNotFound, APIError
from node.utils import get_logger
from node.storage.db.db import update_db_with_status_sync
from node.celery_worker.utils import handle_ipfs_input, BASE_OUTPUT_DIR

logger = get_logger(__name__)


def prepare_volume_directory(
    base_dir: str,
    bind_path: str,
    mode: str,
    job_id: Optional[str] = None,
    input_dir: Optional[str] = None,
    input_ipfs_hash: Optional[str] = None,
) -> Dict:
    """Prepare a volume directory"""
    if input_dir and input_ipfs_hash:
        raise ValueError("Only one of input_dir and input_ipfs_hash can be set")
    if input_dir:
        local_path = f"{base_dir}/{input_dir}"
        if not os.path.exists(local_path):
            raise ValueError(f"Input directory {input_dir} does not exist")
        return {local_path: {"bind": bind_path, "mode": mode}}
    elif input_ipfs_hash:
        local_path = handle_ipfs_input(input_ipfs_hash)
        return {local_path: {"bind": bind_path, "mode": mode}}
    elif job_id:
        local_path = f"{base_dir}/{job_id}"
        if not os.path.exists(local_path):
            os.makedirs(local_path)
        return {local_path: {"bind": bind_path, "mode": mode}}
    else:
        return {}


def monitor_container_logs(container: Container, job: Dict) -> str:
    """Monitor container logs"""
    output = ""
    for line in container.logs(stream=True, follow=True):
        output += line.strip().decode("utf-8") + "\n"
        job["status"] = "running"
        asyncio.run(update_db_with_status_sync(job_data=job))

    job["status"] = "completed"
    job["reply"] = {"output": output}
    job["error"] = False
    job["error_message"] = ""
    job["completed_time"] = datetime.now(pytz.utc).isoformat()
    asyncio.run(update_db_with_status_sync(job_data=job))
    time.sleep(5)

    return output


def cleanup_container(container: Container) -> None:
    """Cleanup a container"""
    logger.info(f"Removing container: {container}")
    if container:
        container.stop()
        container.remove()


def run_container_job(job: Dict = None, **kwargs) -> None:
    """
        Run a docker container
        :param job: Job details
        :param node_config: Node config
    =    :param kwargs: Additional kwargs
    """
    """
    Example job:
    {
        'id': '1',
        'docker_image': 'nbs-test',
        'docker_command': 'python3 test.py',
        'docker_volumes': {'/home/': {'bind': '/home/', 'mode': 'rw'}}
        'docker_num_gpus': 0,
        'docker_env_vars': {'TEST': 'test'},
        'kwargs': {}
    }
    """
    docker_params = job["docker_params"]  # Dict
    image = docker_params["docker_image"]  # str
    command = docker_params["docker_command"]  # str
    input_dir = docker_params.get("input_dir", None)
    input_ipfs_hash = docker_params.get("input_ipfs_hash", None)
    bind_input_dir = docker_params.get("bind_input_dir", None)
    bind_output_dir = docker_params.get("bind_output_dir", None)
    num_gpus = docker_params.get("docker_num_gpus", 0)  # int 0 for none -1 for all
    env_vars = docker_params.get("docker_env_vars", None)  # Union[Dict, None]

    volumes = {}
    if input_dir or input_ipfs_hash:
        logger.info("Preparing input directory")
        inp_vol = prepare_volume_directory(
            base_dir=BASE_OUTPUT_DIR,
            bind_path=bind_input_dir,
            mode="ro",
            input_dir=input_dir,
            input_ipfs_hash=input_ipfs_hash,
        )
        volumes.update(inp_vol)

    if bind_output_dir:
        logger.info("Preparing output directory")
        out_vol = prepare_volume_directory(
            base_dir=BASE_OUTPUT_DIR,
            job_id=job["id"].split(":")[1],
            bind_path=bind_output_dir,
            mode="rw",
        )
        volumes.update(out_vol)

    client = docker.from_env()

    # if kwargs does not exist, create it
    if not kwargs:
        kwargs = {}

    try:
        # GPU allocation
        if num_gpus != 0:
            gpu_request = DeviceRequest(count=num_gpus, capabilities=[["gpu"]])
            kwargs["device_requests"] = [gpu_request]

        # Environment variables
        if env_vars:
            kwargs["environment"] = env_vars

        # Volumes
        if volumes:
            kwargs["volumes"] = volumes

        logger.debug(f"Running container with kwargs: {kwargs}")

        container = client.containers.run(
            image=image, 
            command=command, 
            detach=True, 
            **kwargs
        )

        output = monitor_container_logs(container, job)

        # Update the job status to completed
        logger.info(f"Container finished running: {container}")

        job["status"] = "completed"
        job["reply"] = {"output": str(output)}
        job["error"] = False
        job["error_message"] = ""
        job["completed_time"] = datetime.now(pytz.utc).isoformat()

        asyncio.run(
            update_db_with_status_sync(
                job_data=job,
            )
        )
        logger.info(f"Container job completed: {job}")

    except (ContainerError, ImageNotFound, APIError) as e:
        logger.error(f"An error occurred: {str(e)}")

        job["status"] = "error"
        job["reply"] = {
            "output": str(
                container.logs(stdout=True, stderr=False).decode().strip()
                if container
                else ""
            )
        }
        job["error"] = True
        job["error_message"] = str(e)
        job["completed_time"] = datetime.now(pytz.utc).isoformat()

        asyncio.run(
            update_db_with_status_sync(
                job_data=job,
            )
        )

    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")

        job["status"] = "error"
        job["reply"] = {
            "output": str(
                container.logs(stdout=True, stderr=False).decode().strip()
                if container
                else ""
            )
        }
        job["error"] = True
        job["error_message"] = str(e)
        job["completed_time"] = datetime.now(pytz.utc).isoformat()

        # Update the job status to error
        asyncio.run(
            update_db_with_status_sync(
                job_data=job,
            )
        )

    finally:
        logger.info(f"Celery task done for job: {job}")
        logger.info(f"Done. Removing container: {container}")
        if container:
            cleanup_container(container)
