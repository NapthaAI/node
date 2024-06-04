import os
import asyncio
import time
from typing import Dict, Optional
from datetime import datetime
import pytz
import json
import docker
from docker.types import DeviceRequest
from docker.models.containers import Container
from docker.errors import ContainerError, ImageNotFound, APIError
from naptha_sdk.schemas import DockerParams, ModuleRun
from node.utils import get_logger
from node.worker.main import app
from node.worker.utils import handle_ipfs_input, BASE_OUTPUT_DIR, update_db_with_status_sync, upload_to_ipfs
import traceback

logger = get_logger(__name__)


def prepare_volume_directory(
    base_dir: str,
    bind_path: str,
    mode: str,
    module_run_id: Optional[str] = None,
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
    elif module_run_id:
        local_path = f"{base_dir}/{module_run_id}"
        if not os.path.exists(local_path):
            os.makedirs(local_path)
        return {local_path: {"bind": bind_path, "mode": mode}}
    else:
        return {}


def monitor_container_logs(
        container: Container, 
        module_run: Dict, 
        save_location: Optional[str] = None
    ) -> str:
    """Monitor container logs"""
    output = ""
    for line in container.logs(stream=True, follow=True):
        output += line.strip().decode("utf-8") + "\n"
        module_run.status = "running"
        asyncio.run(update_db_with_status_sync(module_run=module_run))

    if save_location == "node":
        out_msg = {
            "output": str(output),
            "node_storage_path": module_run.id
        }
    elif save_location == "ipfs":
        out_msg = upload_to_ipfs(f"{BASE_OUTPUT_DIR}/{module_run.id.split(':')[1]}")
        out_msg = {
            "output": str(output),
            "output_ipfs_hash": out_msg
        }
    else:
        out_msg = {
            "output": str(output),
        }

    module_run.status = "completed"
    module_run.results = [out_msg["output"]]
    module_run.error = False
    module_run.error_message = ""
    module_run.completed_time = datetime.now(pytz.utc).isoformat()
    asyncio.run(update_db_with_status_sync(module_run=module_run))
    time.sleep(5)

    return output


def cleanup_container(container: Container) -> None:
    """Cleanup a container"""
    logger.info(f"Removing container: {container}")
    if container:
        container.stop()
        container.remove()


def run_container_module(module_run: ModuleRun = None, **kwargs) -> None:
    """
        Run a docker container
        :param module_run: ModuleRun details
        :param node_config: Node config
    =    :param kwargs: Additional kwargs
    """
    """
    Example module run:
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

    if module_run.module_params.save_location:
        if module_run.module_params.save_location not in ["node", "ipfs"]:
            raise ValueError("save_location must be either 'node' or 'ipfs'")

    volumes = {}
    if module_run.module_params.input_dir or module_run.module_params.input_ipfs_hash:
        logger.info("Preparing input directory")
        inp_vol = prepare_volume_directory(
            base_dir=BASE_OUTPUT_DIR,
            bind_path=module_run.module_params.bind_input_dir,
            mode="ro",
            input_dir=module_run.module_params.input_dir,
            input_ipfs_hash=module_run.module_params.input_ipfs_hash,
        )
        volumes.update(inp_vol)

    if module_run.module_params.docker_output_dir:
        logger.info("Preparing output directory")
        out_vol = prepare_volume_directory(
            base_dir=BASE_OUTPUT_DIR,
            module_run_id=module_run.id.split(":")[1],
            bind_path=module_run.module_params.docker_output_dir,
            mode="rw",
        )
        volumes.update(out_vol)

    client = docker.from_env()

    # if kwargs does not exist, create it
    if not kwargs:
        kwargs = {}

    try:
        # GPU allocation
        if module_run.module_params.docker_num_gpus != 0:
            gpu_request = DeviceRequest(count=module_run.module_params.docker_num_gpus, capabilities=[["gpu"]])
            kwargs["device_requests"] = [gpu_request]

        # Environment variables
        if module_run.module_params.docker_env_vars:
            kwargs["environment"] = module_run.module_params.docker_env_vars

        # Volumes
        if volumes:
            kwargs["volumes"] = volumes

        logger.debug(f"Running container with kwargs: {kwargs}")

        container = client.containers.run(
            image=module_run.module_params.docker_image, 
            command=module_run.module_params.docker_command, 
            detach=True, 
            **kwargs
        )

        output = monitor_container_logs(container, module_run, save_location=module_run.module_params.save_location)
    
        # Update the module_run status to completed
        logger.info(f"Container finished running: {container}")
        logger.info(f"Container module run completed: {module_run}")

    except (ContainerError, ImageNotFound, APIError) as e:
        logger.error(f"An error occurred: {str(e)}")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")

        module_run.status = "error"
        module_run.results = {
            "output": str(
                container.logs(stdout=True, stderr=False).decode().strip()
                if container
                else ""
            )
        }
        module_run.error = True
        module_run.error_message = str(e) + error_details
        module_run.completed_time = datetime.now(pytz.utc).isoformat()

        asyncio.run(
            update_db_with_status_sync(
                module_run=module_run,
            )
        )

    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")

        module_run.status = "error"
        module_run.results = {
            "output": str(
                container.logs(stdout=True, stderr=False).decode().strip()
                if container
                else ""
            )
        }
        module_run.error = True
        module_run.error_message = str(e) + error_details
        module_run.completed_time = datetime.now(pytz.utc).isoformat()

        # Update the module run status to error
        asyncio.run(
            update_db_with_status_sync(
                module_run=module_run,
            )
        )

    finally:
        logger.info(f"Celery task done for module run: {module_run}")
        logger.info(f"Done. Removing container: {container}")
        if container:
            cleanup_container(container)

# Function to execute a docker module
@app.task
def execute_docker_module(module_run: Dict) -> None:
    """
    Execute a docker module
    :param module_run: ModuleRun details
    :param hub_config: Hub config
    """
    module_run = ModuleRun(**module_run)
    module_run.module_params = DockerParams(**module_run.module_params)
    logger.info(f"Executing docker module run: {module_run}")

    module_run.status = "processing"
    module_run.start_processing_time = datetime.now(pytz.utc).isoformat()

    # Update the module run status to processing
    asyncio.run(
        update_db_with_status_sync(
            module_run=module_run,
        )
    )
    try:
        run_container_module(
            module_run=module_run,
        )

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")