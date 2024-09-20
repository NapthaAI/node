import logging
import os
import requests
from pathlib import Path
import subprocess
from typing import List


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

