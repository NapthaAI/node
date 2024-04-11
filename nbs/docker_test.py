import logging
import docker
from typing import Union, Dict
from docker.types import DeviceRequest
from docker.errors import ContainerError, ImageNotFound, APIError


def get_logger(name: str, level: int = logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


client = docker.from_env()
logger = get_logger(__name__)


def run_container(
    image: str,  # Image name
    command: str,  # Command to run
    volumes: Union[Dict, None] = None,  # Volumes to mount
    num_gpus: int = 0,  # Number of GPUs to allocate -1 for all 0 for none
    env_vars: Union[
        Dict, None
    ] = None,  # Environment variables to pass to the container
    **kwargs,
):
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

        print(kwargs)

        container = client.containers.run(
            image=image, command=command, detach=True, **kwargs
        )

        for line in container.logs(stream=True, follow=True):
            logger.info(line.strip().decode("utf-8"))

    except (ContainerError, ImageNotFound, APIError) as e:
        logger.error(f"An error occurred: {str(e)}")
        pass

    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        pass

    finally:
        logger.info("Done.")
        if container:
            container.stop()
            container.remove()


# Example usage
if __name__ == "__main__":
    envs = {"env1": "value1", "env2": "value2"}
    volumes = {
        "/Users/arshath/play/cnode/input_folder": {"bind": "/inputs", "mode": "rw"},
        "/Users/arshath/play/cnode/output_folder": {"bind": "/outputs", "mode": "rw"},
    }
    run_container(
        image="sum-app",
        command="python -u sum.py --num1 10 --num2 20",
        volumes=volumes,
        num_gpus=0,
        env_vars=envs,
    )
