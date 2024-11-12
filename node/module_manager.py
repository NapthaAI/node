from contextlib import contextmanager
import fcntl
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError
import importlib
from node.worker.utils import download_from_ipfs, unzip_file
from node.config import AGENTS_SOURCE_DIR
import logging
import os
from pathlib import Path
import subprocess
import time
import traceback
from typing import List

logger = logging.getLogger(__name__)

INSTALLED_MODULES = {}

class LockAcquisitionError(Exception):
    pass

@contextmanager
def file_lock(lock_file, timeout=30):
    lock_fd = None
    try:
        # Ensure the directory exists
        lock_dir = os.path.dirname(lock_file)
        os.makedirs(lock_dir, exist_ok=True)

        start_time = time.time()
        while True:
            try:
                lock_fd = open(lock_file, "w")
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except IOError:
                if time.time() - start_time > timeout:
                    raise LockAcquisitionError(
                        f"Failed to acquire lock after {timeout} seconds"
                    )
                time.sleep(1)

        yield lock_fd

    finally:
        if lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

def is_agent_installed(agent_name: str, required_version: str) -> bool:
    try:
        importlib.import_module(agent_name)
        agents_source_dir = os.path.join(AGENTS_SOURCE_DIR, agent_name)

        if not Path(agents_source_dir).exists():
            logger.warning(f"Agents source directory for {agent_name} does not exist")
            return False

        try:
            repo = Repo(agents_source_dir)
            if repo.head.is_detached:
                current_tag = next(
                    (tag.name for tag in repo.tags if tag.commit == repo.head.commit),
                    None,
                )
            else:
                current_tag = next(
                    (tag.name for tag in repo.tags if tag.commit == repo.head.commit),
                    None,
                )

            if current_tag:
                logger.info(f"Agent {agent_name} is at tag: {current_tag}")
                current_version = (
                    current_tag[1:] if current_tag.startswith("v") else current_tag
                )
                required_version = (
                    required_version[1:]
                    if required_version.startswith("v")
                    else required_version
                )
                return current_version == required_version
            else:
                logger.warning(f"No tag found for current commit in {agent_name}")
                return False
        except (InvalidGitRepositoryError, GitCommandError) as e:
            logger.error(f"Git error for {agent_name}: {str(e)}")
            return False

    except ImportError:
        logger.warning(f"Agent {agent_name} not found")
        return False

async def install_agent_if_not_present(flow_run_obj, agent_version):
    agent_name = flow_run_obj.agent_name
    if agent_name in INSTALLED_MODULES:
        installed_version = INSTALLED_MODULES[agent_name]
        if installed_version == agent_version:
            logger.info(
                f"Agent {agent_name} version {agent_version} is already installed"
            )
            return True

    lock_file = Path(AGENTS_SOURCE_DIR) / f"{agent_name}.lock"
    logger.info(f"Lock file: {lock_file}")
    try:
        with file_lock(lock_file):
            logger.info(f"Acquired lock for {agent_name}")

            if not is_agent_installed(agent_name, agent_version):
                logger.info(
                    f"Agent {agent_name} version {agent_version} is not installed. Attempting to install..."
                )
                if not flow_run_obj.agent_source_url:
                    raise ValueError(
                        f"Agent URL is required for installation of {agent_name}"
                    )
                install_agent_if_needed(
                    agent_name, agent_version, flow_run_obj.agent_source_url
                )

            # Verify agent installation
            if not verify_agent_installation(agent_name):
                raise RuntimeError(
                    f"Agent {agent_name} failed verification after installation"
                )

            # Install personas if they exist in flow_run_obj
            if hasattr(flow_run_obj, 'personas_urls') and flow_run_obj.personas_urls:
                logger.info(f"Installing personas for agent {agent_name}")
                await install_personas_if_needed(agent_name, flow_run_obj.personas_urls)

            logger.info(
                f"Agent {agent_name} version {agent_version} is installed and verified"
            )
            INSTALLED_MODULES[agent_name] = agent_version
    except LockAcquisitionError as e:
        error_msg = f"Failed to acquire lock for agent {agent_name}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = f"Failed to install or verify agent {agent_name}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e

def verify_agent_installation(agent_name: str) -> bool:
    try:
        importlib.import_module(f"{agent_name}.run")
        return True
    except ImportError as e:
        logger.error(f"Error importing agent {agent_name}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


async def install_personas_if_needed(agent_name: str, personas_urls: List[str]):
    if not personas_urls:
        logger.info("No personas to install")
        return
        
    personas_base_dir = Path(AGENTS_SOURCE_DIR) / "personas"
    personas_base_dir.mkdir(exist_ok=True)
    
    logger.info(f"Installing personas for agent {agent_name}")
    
    for persona_url in personas_urls:
        try:
            # Extract repo name from URL
            repo_name = persona_url.split('/')[-1]
            persona_dir = personas_base_dir / repo_name
            
            if persona_dir.exists():
                logger.info(f"Updating existing persona repository: {repo_name}")
                repo = Repo(persona_dir)
                repo.remotes.origin.fetch()
                repo.git.pull('origin', 'main')  # Assuming main branch
                logger.info(f"Successfully updated persona: {repo_name}")
            else:
                # Clone new repository
                logger.info(f"Cloning new persona repository: {repo_name}")
                Repo.clone_from(persona_url, persona_dir)
                logger.info(f"Successfully cloned persona: {repo_name}")

        except Exception as e:
            error_msg = f"Error installing persona from {persona_url}: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Continue with other personas even if one fails
            continue


def install_agent_from_ipfs(agent_name: str, agent_version: str, agent_source_url: str):
    logger.info(f"Installing/updating agent {agent_name} version {agent_version}")
    agents_source_dir = Path(AGENTS_SOURCE_DIR) / agent_name
    logger.info(f"Agent path exists: {agents_source_dir.exists()}")
    try:
        agent_ipfs_hash = agent_source_url.split("ipfs://")[1]
        agent_temp_zip_path = download_from_ipfs(agent_ipfs_hash, AGENTS_SOURCE_DIR)
        unzip_file(agent_temp_zip_path, agents_source_dir)
        os.remove(agent_temp_zip_path)

    except Exception as e:
        error_msg = f"Error installing {agent_name}: {str(e)}"
        logger.error(error_msg)
        logger.info(f"Traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e


def install_agent_from_git(agent_name: str, agent_version: str, agent_source_url: str):
    logger.info(f"Installing/updating agent {agent_name} version {agent_version}")
    agents_source_dir = Path(AGENTS_SOURCE_DIR) / agent_name
    logger.info(f"Agent path exists: {agents_source_dir.exists()}")
    try:
        if agents_source_dir.exists():
            logger.info(f"Updating existing repository for {agent_name}")
            repo = Repo(agents_source_dir)
            repo.remotes.origin.fetch()
            repo.git.checkout(agent_version)
            logger.info(f"Successfully updated {agent_name} to version {agent_version}")
        else:
            # Clone new repository
            logger.info(f"Cloning new repository for {agent_name}")
            Repo.clone_from(agent_source_url, agents_source_dir)
            repo = Repo(agents_source_dir)
            repo.git.checkout(agent_version)
            logger.info(f"Successfully cloned {agent_name} version {agent_version}")

    except Exception as e:
        error_msg = f"Error installing {agent_name}: {str(e)}"
        logger.error(error_msg)
        logger.info(f"Traceback: {traceback.format_exc()}")
        if "Dependency conflict detected" in str(e):
            error_msg += "\nThis is likely due to a mismatch in naptha-sdk versions between the agent and the main project."
        raise RuntimeError(error_msg) from e
    
def run_poetry_command(command):
    try:
        result = subprocess.run(
            ["poetry"] + command, check=True, capture_output=True, text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        error_msg = f"Poetry command failed: {e.cmd}"
        logger.error(error_msg)
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        raise RuntimeError(error_msg)

def install_agent_if_needed(agent_name: str, agent_version: str, agent_source_url: str):
    logger.info(f"Installing/updating agent {agent_name} version {agent_version}")
    
    agents_source_dir = Path(AGENTS_SOURCE_DIR) / agent_name
    logger.info(f"Agent path exists: {agents_source_dir.exists()}")

    try:
        if "ipfs://" in agent_source_url:
            install_agent_from_ipfs(agent_name, agent_version, agent_source_url)
        else:
            install_agent_from_git(agent_name, agent_version, agent_source_url)
            
        # Reinstall the agent
        logger.info(f"Installing/Reinstalling {agent_name}")
        installation_output = run_poetry_command(["add", f"{agents_source_dir}"])
        logger.info(f"Installation output: {installation_output}")

        if not verify_agent_installation(agent_name):
            raise RuntimeError(
                f"Agent {agent_name} failed verification after installation"
            )

        logger.info(
            f"Successfully installed and verified {agent_name} version {agent_version}"
        )
    except Exception as e:
        error_msg = f"Error installing {agent_name}: {str(e)}"
        logger.error(error_msg)
        logger.info(f"Traceback: {traceback.format_exc()}")
        if "Dependency conflict detected" in str(e):
            error_msg += "\nThis is likely due to a mismatch in naptha-sdk versions between the agent and the main project."
        raise RuntimeError(error_msg) from e
