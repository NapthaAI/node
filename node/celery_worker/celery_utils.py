import asyncio
from datetime import datetime
import docker
from dotenv import load_dotenv
from docker.errors import ContainerError, ImageNotFound, APIError
from docker.types import DeviceRequest
import importlib
import importlib.util
from node.storage.db.db import update_db_with_status_sync
from node.utils import get_logger
import os
from pathlib import Path
import pytz
import subprocess
import time
from typing import Dict, List
import yaml

load_dotenv()

logger = get_logger(__name__)

logger.info(os.getenv("STABILITY_API_KEY"))
# Get file path
BASE_ROOT_DIR = os.getcwd()
FILE_PATH = Path(__file__).resolve()
CELERY_WORKER_DIR = FILE_PATH.parent
NODE_DIR = CELERY_WORKER_DIR.parent
MODULES_PATH = f"{NODE_DIR}/{os.getenv('MODULES_PATH')}"
BASE_OUTPUT_DIR = os.getenv("BASE_OUTPUT_DIR")

if not os.path.isabs(BASE_OUTPUT_DIR):
    # remove . from the path
    BASE_OUTPUT_DIR = BASE_OUTPUT_DIR.replace(".", "")
    BASE_OUTPUT_DIR = f"{NODE_DIR}/{BASE_OUTPUT_DIR}"
    logger.info(f"BASE_OUTPUT_DIR: {BASE_OUTPUT_DIR}")


def run_container(job: Dict = None, **kwargs) -> None:
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
    input_dir = docker_params.get("docker_input_dir", None)  # Union[str, None]
    output_dir = docker_params.get("docker_output_dir", None)  # Union[str, None]
    num_gpus = docker_params.get("docker_num_gpus", 0)  # int 0 for none -1 for all
    env_vars = docker_params.get("docker_env_vars", None)  # Union[Dict, None]

    volumes = {}
    if input_dir:
        logger.info("Preparing input directory")
        # Split job id
        job_id = job["id"].split(":")[1]
        # Local path should be base_output_dir + job_id
        local_input_dir = f"{BASE_OUTPUT_DIR}/{job_id}"
        volumes[local_input_dir] = {"bind": input_dir, "mode": "ro"}

        # if local path does not exist, create it
        if not os.path.exists(local_input_dir):
            os.makedirs(local_input_dir)

    if output_dir:
        logger.info("Preparing output directory")
        # Split job id
        job_id = job["id"].split(":")[1]
        # Local path should be base_output_dir + job_id
        local_output_dir = f"{BASE_OUTPUT_DIR}/{job_id}"
        volumes[local_output_dir] = {"bind": output_dir, "mode": "rw"}

        # if local path does not exist, create it
        if not os.path.exists(local_output_dir):
            os.makedirs(local_output_dir)

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
            image=image, command=command, detach=True, **kwargs
        )

        output = ""
        for line in container.logs(stream=True, follow=True):
            output += line.strip().decode("utf-8") + "\n"
            job["status"] = "running"
            # job['error'] = False
            # job['error_message'] = ""

            logger.info(f"Updating hub with job status: {job}")

            asyncio.run(
                update_db_with_status_sync(
                    job_data=job,
                )
            )

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
        # sleep for 5 seconds to allow the logs to be sent to the hub
        time.sleep(5)

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
            container.stop()
            container.remove()


def run_subprocess(cmd: List) -> None:
    """
    Run a subprocess
    :param cmd: Command to run
    """
    logger.info(f"Running subprocess: {cmd}")
    try:
        out, err = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ).communicate()

        # Log the output
        logger.info(f"Subprocess output: {out.decode('utf-8')}")

        if err:
            logger.info(f"Subprocess error: {err.decode('utf-8')}")
            raise Exception(err)

        return out.decode("utf-8")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise e


def run_template(job: Dict) -> None:
    """
    Run a template job
    :param job: Job details
    :param hub_config: Hub config
    """
    try:
        # Log current working directory
        logger.info(f"Running template job: {job}")

        # update the job status to running
        job["status"] = "running"
        asyncio.run(
            update_db_with_status_sync(
                job_data=job,
            )
        )

        template_name = job["module_id"]
        template_args = job["module_params"]
        template_path = f"{MODULES_PATH}/{template_name}"

        # check if there is input_dir in the template_args
        input_dir = template_args.get("input_dir", None)

        # if input_dir exists, create the local path
        if input_dir:
            input_dir = f"{BASE_OUTPUT_DIR}/{input_dir}"
            template_args["input_dir"] = input_dir

            # raise if local path does not exist
            if not os.path.exists(input_dir):
                raise Exception(f"Local input directory does not exist: {input_dir}")

        cfg_path = f"{template_path}/{template_name}/component.yaml"
        with open(cfg_path, "r") as file:
            cfg = yaml.load(file, Loader=yaml.FullLoader)

        # re template-name to template_path
        tn = template_name.replace("-", "_")

        entrypoint = cfg["implementation"]["package"]["entrypoint"].split(".")[0]

        # Dynamically import the main module of the template
        main_module = importlib.import_module(f"{tn}.run")
        main_func = getattr(main_module, entrypoint)
        logger.info(f"Main function: {main_func}")

        # Dynamically load InputSchema from the corresponding template's schemas.py
        schemas_module = importlib.import_module(f"{tn}.schemas")
        InputSchema = getattr(schemas_module, "InputSchema")

        # add output_path to the template_args if save is True
        save = template_args.get("save", False)
        if save:
            output_path = f"{BASE_OUTPUT_DIR}/{job['id'].split(':')[1]}"
            template_args["output_path"] = output_path

            # if output path does not exist, create it
            if not os.path.exists(output_path):
                os.makedirs(output_path)

        # Validate the job data with the loaded schema
        validated_data = InputSchema(**template_args)

        # Execute the job
        results = main_func(validated_data, cfg)

        return results

    except Exception as e:
        # Change directory back to root
        os.chdir(BASE_ROOT_DIR)

        logger.error(f"An error occurred: {e}")
        raise e
