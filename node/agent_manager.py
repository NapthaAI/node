from git import Repo
import json
import os
from pathlib import Path
import shutil
import logging
from node.config import AGENTS_SOURCE_DIR
from node.utils import run_subprocess

logger = logging.getLogger(__name__)

PARENT_DIR = Path(__file__).resolve().parent
logger.info(f"AGENTS_SOURCE_DIR: {AGENTS_SOURCE_DIR}")


def clone_repo(
    tag,
    agent_name,
    url=None,
    clone_dir=AGENTS_SOURCE_DIR,
):
    logger.info(f"Cloning repo {url} with tag {tag} to {clone_dir}")
    repo_path = Path(clone_dir) / agent_name
    repo = Repo.clone_from(url, repo_path)
    logger.info(f"Checking out tag {tag}")
    repo.git.checkout(tag)
    logger.info(f"Done cloning repo {url} with tag {tag} to {clone_dir}")


def install_agent(package_name, agents_source_dir=AGENTS_SOURCE_DIR):
    # Get the path to the package
    package_path = f"{agents_source_dir}/{package_name}"

    # resolve to full path
    package_path = os.path.abspath(package_path)
    logger.info(f"Installing agent {package_name} from {package_path}")

    # Use subprocess to add the package to the poetry environment
    run_subprocess(["poetry", "add", f"{package_path}"])

    # Use subprocess to install the package dependencies
    run_subprocess(["poetry", "install"])


def install_agents_from_config(agents_config_path):
    logger.info(f"Downloading AI agents in {agents_config_path}")
    # Make sure the agents source directory is empty
    if os.path.exists(AGENTS_SOURCE_DIR):
        shutil.rmtree(AGENTS_SOURCE_DIR)
    with open(agents_config_path) as f:
        agents_config_file = json.load(f)

    for package, url in agents_config_file.items():
        # Download the agent
        parts = package.split("/")
        package_name = parts[1]
        tag = "v" + package.split("/")[-1]
        try:
            clone_repo(tag=tag, url=url, agent_name=package_name)
        except Exception as e:
            logger.error(f"Failed to clone repo: {e}")
            raise e

        # Install the agent
        try:
            install_agent(package_name)
        except Exception as e:
            logger.error(f"Failed to install agent: {e}")
            raise e

    logger.info(f"Done downloading and installing AI agents in {agents_config_path}")
