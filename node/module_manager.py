from contextlib import contextmanager
import fcntl
import shutil
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError
import importlib
import json
from node.schemas import AgentDeployment, LLMConfig
from node.worker.utils import download_from_ipfs, unzip_file
from node.config import AGENTS_SOURCE_DIR, BASE_OUTPUT_DIR
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

async def install_agent_if_not_present(agent_run, agent_version):
    agent_name = agent_run.agent_deployment.module["id"].split(":")[-1]
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
                if not agent_run.agent_deployment.module["url"]:
                    raise ValueError(
                        f"Agent URL is required for installation of {agent_name}"
                    )
                install_agent_if_needed(
                    agent_name, agent_version, agent_run.agent_deployment.module["url"]
                )

            # Verify agent installation
            if not verify_agent_installation(agent_name):
                raise RuntimeError(
                    f"Agent {agent_name} failed verification after installation"
                )

            # Install personas if they exist in agent_run
            if hasattr(agent_run, 'personas_urls') and agent_run.agent_deployment.module["personas_urls"]:
                logger.info(f"Installing personas for agent {agent_name}")
                await install_personas_if_needed(agent_name, agent_run.agent_deployment.module["personas_urls"])

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
    

async def install_personas_if_needed(personas_urls: List[str]):
    if not personas_urls:
        logger.info("No personas to install")
        return


    personas_base_dir = Path(AGENTS_SOURCE_DIR) / "personas"
    personas_base_dir.mkdir(exist_ok=True)

    for persona_url in personas_urls:
        logger.info(f"Installing persona {persona_url}")
        if persona_url in ["", None, " "]:
            logger.warning(f"Skipping empty persona URL")
            continue
        # identify if the persona is a git repo or an ipfs hash
        if "ipfs://" in persona_url:
            await install_persona_from_ipfs(persona_url, personas_base_dir)
        else:
            persona_dir = await install_persona_from_git(persona_url, personas_base_dir)
        return persona_dir
        
async def install_persona_from_ipfs(persona_url: str, personas_base_dir: Path):
    try:
        if "::" not in persona_url:
            raise ValueError(f"Invalid persona URL: {persona_url}. Expected format: ipfs://ipfs_hash::persona_folder_name")
        
        persona_folder_name = persona_url.split("::")[1]
        persona_ipfs_hash = persona_url.split("::")[0].split("ipfs://")[1]
        persona_dir = personas_base_dir / persona_folder_name

        # if the persona directory exists, continue without downloading
        if persona_dir.exists():
            logger.info(f"Persona {persona_folder_name} already exists")
            # remove the directory
            shutil.rmtree(persona_dir)
            logger.info(f"Removed existing persona directory: {persona_dir}")

        persona_temp_zip_path = download_from_ipfs(persona_ipfs_hash, personas_base_dir)
        unzip_file(persona_temp_zip_path, persona_dir)
        os.remove(persona_temp_zip_path)
        logger.info(f"Successfully installed persona: {persona_folder_name}")
        return persona_dir
    except Exception as e:
        error_msg = f"Error installing persona from {persona_url}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e

async def install_persona_from_git(repo_url: str, personas_base_dir: Path):
    try:
        repo_name = repo_url.split('/')[-1]
        persona_dir = personas_base_dir / repo_name

        if persona_dir.exists():
            # remove the directory
            shutil.rmtree(persona_dir)
            logger.info(f"Removed existing persona directory: {persona_dir}")
            # clone the repository again
            Repo.clone_from(repo_url, persona_dir)
            logger.info(f"Successfully cloned persona: {repo_name}")
        else:
            logger.info(f"Cloning new persona repository: {repo_name}")
            Repo.clone_from(repo_url, persona_dir)
            logger.info(f"Successfully cloned persona: {repo_name}")
        return persona_dir
    except Exception as e:
        error_msg = f"Error installing persona from {repo_url}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e


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

def load_persona(persona_dir):
    """Load persona from a JSON file in a git repository."""
    try:
        persona_dir = Path(persona_dir)
        # Get list of JSON files in repo using pathlib
        json_files = list(persona_dir.rglob("*.json"))
                
        if not json_files:
            logger.error(f"No JSON files found in repository {persona_dir}")
            return None
            
        # Load the first JSON file found
        persona_file = json_files[0]
        with persona_file.open('r') as f:
            persona_data = json.load(f)
            
        return persona_data
        
    except Exception as e:
        logger.error(f"Error loading persona from {persona_dir}: {e}")
        return None

def load_llm_configs(llm_configs_path):
    with open(llm_configs_path, "r") as file:
        llm_configs = json.loads(file.read())
    return [LLMConfig(**config) for config in llm_configs]

def load_agent_deployments(agent_deployments_path, module):
    with open(agent_deployments_path, "r") as file:
        agent_deployments = json.loads(file.read())

    for deployment in agent_deployments:
        deployment["module"] = module
        # Load LLM config
        config_name = deployment["agent_config"]["llm_config"]["config_name"]
        config_path = agent_deployments_path.parent / "llm_configs.json"
        llm_configs = load_llm_configs(config_path)
        llm_config = next(config for config in llm_configs if config.config_name == config_name)
        deployment["agent_config"]["llm_config"] = llm_config   

        # Load persona
        persona_dir = install_personas_if_needed([deployment["agent_config"]["persona_module"]["url"]])
        persona_data = load_persona(persona_dir)
        deployment["agent_config"]["persona_module"]["data"] = persona_data

    return [AgentDeployment(**deployment) for deployment in agent_deployments]

def load_and_validate_input_schema(agent_run):
    """Loads and validates the input schema for the agent"""
    agent_name = agent_run.agent_deployment.module['name'].replace("-", "_")
    schemas_module = importlib.import_module(f"{agent_name}.schemas")
    InputSchema = getattr(schemas_module, "InputSchema")
    agent_run.inputs = InputSchema(**agent_run.inputs)
    return agent_run

async def load_agent(agent_run):
    """Loads the agent and returns the agent function, validated data and config"""
    # Load the agent from the agents directory
    agent_name = agent_run.agent_deployment.module['name']
    agent_path = Path(f"{AGENTS_SOURCE_DIR}/{agent_name}")

    # Load configs
    agent_deployment = load_agent_deployments(agent_path / agent_name / "configs/agent_deployments.json", agent_run.agent_deployment.module)[0]
    agent_run.agent_deployment = agent_deployment

    # Handle output configuration
    if agent_deployment.data_generation_config.save_outputs:
        if ':' in agent_run.id:
            output_path = f"{BASE_OUTPUT_DIR}/{agent_run.id.split(':')[1]}"
        else:
            output_path = f"{BASE_OUTPUT_DIR}/{agent_run.id}"
        agent_run.agent_deployment.data_generation_config.save_outputs_path = output_path
        if not os.path.exists(output_path):
            os.makedirs(output_path)

    agent_run = load_and_validate_input_schema(agent_run)
    
    # Load the agent function
    agent_name = agent_name.replace("-", "_")
    entrypoint = agent_deployment.module["entrypoint"].split(".")[0]
    main_module = importlib.import_module(f"{agent_name}.run")
    main_module = importlib.reload(main_module)
    agent_func = getattr(main_module, entrypoint)
    
    return agent_func, agent_run