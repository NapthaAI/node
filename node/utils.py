from dotenv import load_dotenv
import logging
from node.schemas import NodeConfig
from node.user import get_public_key
import os
import platform
import psutil
import requests
from pathlib import Path
import subprocess
from typing import List

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

logger = get_logger(__name__)

def get_external_ip():
    """Get the external IP address of the node. If the IP address is not found, raise an error."""
    try:
        response = requests.get("https://api.ipify.org", timeout=15)
        return response.text
    except requests.RequestException as e:
        raise f"""Error retrieving IP: {e}\n\nPlease pass the IP address manually in the .env file"""

def parse_ports(port_string: str) -> List[int]:
    """Parse a comma-separated string of ports into a list of integers."""
    return [int(port.strip()) for port in port_string.split(',') if port.strip()]

def get_config():
    """Get the configuration for the node."""
    config = {}

    # Basic Node Configuration
    config["PRIVATE_KEY"] = os.getenv("PRIVATE_KEY")
    config["PUBLIC_KEY"] = get_public_key(config["PRIVATE_KEY"])
    config["IN_DOCKER"] = os.getenv("IN_DOCKER", "false").lower() == "true"
    config["GPU"] = os.getenv("GPU", "false").lower() == "true"
    config["DOCKER_JOBS"] = os.getenv("DOCKER_JOBS", "false").lower() == "true"

    # Node Type and Network Configuration
    config["NODE_TYPE"] = os.getenv("NODE_TYPE", "direct-http")
    logger.info(f"NODE_TYPE: {config['NODE_TYPE']}")
    if config["NODE_TYPE"] in ["direct-http", "direct-ws"]:
        config["NODE_IP"] = os.getenv("NODE_IP")
        config["NODE_PORTS"] = parse_ports(os.getenv("NODE_PORT", "7001"))
        config["NODE_ROUTING"] = None
    elif config["NODE_TYPE"] == "indirect":
        config["NODE_IP"] = None
        config["NODE_PORTS"] = None
        config["NODE_ROUTING"] = os.getenv("NODE_ROUTING")
    else:
        raise Exception("Unknown node type specified in environment.")

    config["NUM_SERVERS"] = int(os.getenv("NUM_SERVERS", 1))

    # MQ Configuration
    config["RMQ_USER"] = os.getenv("RMQ_USER", "username")
    config["RMQ_PASSWORD"] = os.getenv("RMQ_PASSWORD", "password")
    config["CELERY_BROKER_URL"] = os.getenv("CELERY_BROKER_URL", "amqp://localhost:5672/")

    # LLM Configuration
    config["LLM_BACKEND"] = os.getenv("LLM_BACKEND", "ollama")
    config["VLLM_MODEL"] = os.getenv("VLLM_MODEL", None)
    config["OLLAMA_MODELS"] = [item.strip() for item in os.getenv("OLLAMA_MODELS", "").split(",") if item.strip()]
    config["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", None)
    config["STABILITY_API_KEY"] = os.getenv("STABILITY_API_KEY", None)

    # Local DB Configuration
    config["SURREALDB_PORT"] = int(os.getenv("SURREALDB_PORT"))
    config["DB_NS"] = os.getenv("DB_NS")
    config["DB_DB"] = os.getenv("DB_DB")
    config["DB_URL"] = os.getenv("DB_URL")
    config["DB_ROOT_USER"] = os.getenv("DB_ROOT_USER")
    config["DB_ROOT_PASS"] = os.getenv("DB_ROOT_PASS")

    # Storage Configuration
    base_output_dir = os.getenv("BASE_OUTPUT_DIR")
    
    config["BASE_OUTPUT_DIR"] = (NODE_PATH / base_output_dir).resolve()
    if base_output_dir is None:
        raise Exception("BASE_OUTPUT_DIR not found in environment")

    config["MODULES_PATH"] = os.getenv("MODULES_PATH")
    if config["MODULES_PATH"] is None:
        raise Exception("MODULES_PATH not found in environment")

    config["IPFS_GATEWAY_URL"] = os.getenv("IPFS_GATEWAY_URL")
    if config["IPFS_GATEWAY_URL"] is None:
        raise Exception("IPFS_GATEWAY_URL not found in environment")

    # Hub Configuration
    config["LOCAL_HUB"] = os.getenv("LOCAL_HUB", "false").lower() == "true"
    config["LOCAL_HUB_URL"] = os.getenv("LOCAL_HUB_URL")
    config["PUBLIC_HUB_URL"] = os.getenv("PUBLIC_HUB_URL")
    config["HUB_DB_PORT"] = int(os.getenv("HUB_DB_PORT"))
    config["HUB_NS"] = os.getenv("HUB_NS")
    config["HUB_DB"] = os.getenv("HUB_DB")
    config["HUB_ROOT_USER"] = os.getenv("HUB_ROOT_USER")
    config["HUB_ROOT_PASS"] = os.getenv("HUB_ROOT_PASS")
    config["HUB_USERNAME"] = os.getenv("HUB_USERNAME")
    config["HUB_PASSWORD"] = os.getenv("HUB_PASSWORD")

    # System Information
    config["NUM_GPUS"] = os.getenv("NUM_GPUS", 0)
    config["VRAM"] = os.getenv("VRAM", 0)
    config["OS_INFO"] = platform.system()
    config["ARCH_INFO"] = platform.machine()
    config["RAM_INFO"] = psutil.virtual_memory().total

    return config

def get_node_config(config):
    """Get the node configuration."""
    return NodeConfig(
        public_key=config["PUBLIC_KEY"],
        ip=config["NODE_IP"],
        ports=config["NODE_PORTS"],
        routing=config["NODE_ROUTING"],
        ollama_models=config["OLLAMA_MODELS"],
        num_gpus=config["NUM_GPUS"],
        vram=config["VRAM"],
        os=platform.system(),
        arch=platform.machine(),
        ram=psutil.virtual_memory().total,
        docker_jobs=config["DOCKER_JOBS"],
        owner=config["HUB_USERNAME"],
        num_servers=config["NUM_SERVERS"],
        node_type=config["NODE_TYPE"]
    )


def create_output_dir(base_output_dir):
    """Create the output directory for the node."""
    logger.info(f"Creating output directory: {base_output_dir}")
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

def run_subprocess(cmd: List) -> str:
    """Run a subprocess"""
    logger.info(f"Running subprocess: {cmd}")
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True
        )
        out, err = process.communicate()

        # Log the output
        if out:
            logger.info(f"Subprocess output: {out}")

        # Check if there's any stderr output
        if err:
            # Check if it's a pip warning about running as root
            if "WARNING: Running pip as the 'root' user" in err:
                logger.warning(f"Pip warning: {err}")
            else:
                logger.error(f"Subprocess error: {err}")
                raise Exception(err)

        return out

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise

def add_credentials_to_env(username, password):
    env_file_path = os.path.join(os.getcwd(), '.env')
    updated_lines = []
    hub_user_found = False
    hub_pass_found = False

    # Read the existing .env file
    with open(env_file_path, 'r') as env_file:
        for line in env_file:
            if line.startswith('HUB_USERNAME='):
                updated_lines.append(f"HUB_USERNAME={username}\n")
                hub_user_found = True
            elif line.startswith('HUB_PASSWORD='):
                updated_lines.append(f"HUB_PASSWORD={password}\n")
                hub_pass_found = True
            else:
                updated_lines.append(line)

    # Append new credentials if not found
    if not hub_user_found:
        updated_lines.append(f"HUB_USERNAME={username}\n")
    if not hub_pass_found:
        updated_lines.append(f"HUB_PASSWORD={password}\n")

    # Write the updated content back to the .env file
    with open(env_file_path, 'w') as env_file:
        env_file.writelines(updated_lines)

    print("Your credentials have been updated in the .env file. You can now use these credentials to authenticate in future sessions.")

if __name__ == "__main__":
    config = get_config()
    print(config)
