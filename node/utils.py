from dotenv import load_dotenv
import logging
from node.schemas import NodeConfigSchema
import os
import platform
import psutil
import requests
from pathlib import Path

load_dotenv()

FILE_PATH = Path(__file__).resolve()
NODE_PATH = FILE_PATH.parent


def get_logger(name):
    """Get the logger for the node."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


def get_external_ip():
    """Get the external IP address of the node. If the IP address is not found, raise an error."""
    try:
        response = requests.get("https://api.ipify.org", timeout=15)
        return response.text
    except requests.RequestException as e:
        raise f"""Error retrieving IP: {e}\n\nPlease pass the IP address manually in the .env file"""


def get_config():
    """Get the configuration for the node."""
    address = os.getenv("ADDRESS")
    dev_mode = os.getenv("DEV_MODE")
    dev_mode = True if dev_mode == "true" else False

    if not dev_mode:
        if address is None or address == "" or "localhost" in address:
            address = get_external_ip()
            # add http:// to the address
            address = f"http://{address}"

    base_output_dir = os.getenv("BASE_OUTPUT_DIR")
    if base_output_dir is None:
        raise Exception("base_output_dir not found in environment")
    base_output_dir = NODE_PATH / base_output_dir

    base_output_dir = base_output_dir.resolve()

    config = {}
    config["NODE_TYPE"] = os.getenv("NODE_TYPE")
    config["NODE_PORT"] = os.getenv("NODE_PORT")
    config["ADDRESS"] = address
    config["NODE_URL"] = f"{address}:{config["NODE_PORT"]}"
    config["NUM_GPUS"] = os.getenv("NUM_GPUS", 0)
    config["VRAM"] = os.getenv("VRAM", 0)
    config["TEMPLATE_REPO_TAG"] = os.getenv("TEMPLATE_REPO_TAG")
    config["OS_INFO"] = platform.system()
    config["ARCH_INFO"] = platform.machine()
    config["RAM_INFO"] = psutil.virtual_memory().total
    config["BASE_OUTPUT_DIR"] = base_output_dir
    config["MODULES_PATH"] = os.getenv("MODULES_PATH", None)
    config["HUB_USERNAME"] = os.getenv("HUB_USERNAME")
    config["HUB_PASSWORD"] = os.getenv("HUB_PASSWORD")

    config["WORKFLOW_TYPES"] = os.getenv("WORKFLOW_TYPES")
    if config["WORKFLOW_TYPES"] is not None:
        config["WORKFLOW_TYPES"] = config["WORKFLOW_TYPES"].split(",")
    else:
        config["WORKFLOW_TYPES"] = ["docker"]
    return config


def get_node_config(config, token, user_id):
    """Get the node configuration."""
    node_config = NodeConfigSchema(
        user_id=user_id,
        address=f"{config["ADDRESS"]}:{config["NODE_PORT"]}",
        num_gpus=config["NUM_GPUS"],
        vram=config["VRAM"],
        os=config["OS_INFO"],
        arch=config["ARCH_INFO"],
        ram=config["RAM_INFO"],
        workflow_type=config["WORKFLOW_TYPES"],
        token=token,
        id=None,
        template_repo_tag=config["TEMPLATE_REPO_TAG"],
    )
    return node_config


def create_output_dir(base_output_dir):
    """Create the output directory for the node."""
    if base_output_dir is None:
        raise Exception("base_output_dir not found in environment")

    try:
        if not os.path.isabs(base_output_dir):
            file_path = Path(__file__).resolve()
            parent_dir = file_path.parent
            base_output_dir = base_output_dir.replace(".", "")
            base_output_dir = f"{parent_dir}/{base_output_dir}"
            logging.info(f"base_output_dir: {base_output_dir}")

        if not Path(base_output_dir).exists():
            Path(base_output_dir).mkdir(parents=True, exist_ok=True)

        return base_output_dir

    except Exception as e:
        raise Exception(f"Error creating base_output_dir: {e}")


if __name__ == "__main__":
    config = get_config()
    print(config)
