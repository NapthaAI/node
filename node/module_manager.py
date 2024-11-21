from contextlib import contextmanager
import fcntl
import shutil
from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError
import importlib
import json
import logging
import os
from pathlib import Path
import subprocess
import time
import traceback
from typing import List, Union
from node.schemas import (
    AgentDeployment, 
    AgentRun, 
    OrchestratorRun, 
    LLMConfig, 
    AgentConfig
)
from node.worker.utils import download_from_ipfs, unzip_file, load_yaml_config
from node.config import AGENTS_SOURCE_DIR, BASE_OUTPUT_DIR

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

async def install_agent_if_not_present(run: Union[AgentRun, OrchestratorRun], run_version: str):
    if isinstance(run, AgentRun):
        agent_name = run.agent_deployment.module["id"].split(":")[-1]
        url = run.agent_deployment.module["url"]    
    else:
        agent_name = run.orchestrator_deployment.module["id"].split(":")[-1]
        url = run.orchestrator_deployment.module["url"]

    if agent_name in INSTALLED_MODULES:
        installed_version = INSTALLED_MODULES[agent_name]
        if installed_version == run_version:
            logger.info(
                f"Agent {agent_name} version {run_version} is already installed"
            )
            return True

    lock_file = Path(AGENTS_SOURCE_DIR) / f"{agent_name}.lock"
    logger.info(f"Lock file: {lock_file}")
    try:
        with file_lock(lock_file):
            logger.info(f"Acquired lock for {agent_name}")

            if not is_agent_installed(agent_name, run_version):
                logger.info(
                    f"Agent {agent_name} version {run_version} is not installed. Attempting to install..."
                )
                if not url:
                    raise ValueError(
                        f"Agent URL is required for installation of {agent_name}"
                    )
                install_agent_if_needed(
                    agent_name, 
                    run_version, 
                    url
                )

            # Verify agent installation
            if not verify_agent_installation(agent_name):
                raise RuntimeError(
                    f"Agent {agent_name} failed verification after installation"
                )

            # Install personas if they exist in agent_run
            if isinstance(run, AgentRun):
                if hasattr(run, 'personas_urls') and run.agent_deployment.module["personas_urls"]:
                    logger.info(f"Installing personas for agent {agent_name}")
                    await install_personas_if_needed(run.agent_deployment.module["personas_urls"])

            logger.info(
                f"Agent {agent_name} version {run_version} is installed and verified"
            )
            INSTALLED_MODULES[agent_name] = run_version
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
    

async def install_personas_if_needed(personas_url: str):
    if not personas_url:
        logger.info("No personas to install")
        return

    personas_base_dir = Path(AGENTS_SOURCE_DIR) / "personas"
    personas_base_dir.mkdir(exist_ok=True)

    logger.info(f"Installing persona {personas_url}")
    if personas_url in ["", None, " "]:
        logger.warning(f"Skipping empty persona URL")
        return None
    # identify if the persona is a git repo or an ipfs hash
    if "ipfs://" in personas_url:
        return await install_persona_from_ipfs(personas_url, personas_base_dir)
    else:
        return await install_persona_from_git(personas_url, personas_base_dir)
        
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

async def load_agent_deployments(agent_deployments_path, module):
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
        persona_dir = await install_personas_if_needed(deployment["agent_config"]["persona_module"]["url"])
        logger.info(f"Persona directory: {persona_dir}")
        persona_data = load_persona(persona_dir)
        deployment["agent_config"]["persona_module"]["data"] = persona_data

    return [AgentDeployment(**deployment) for deployment in agent_deployments]

async def load_and_validate_input_schema(
    agent_run: AgentRun = None, 
    orchestrator_run: OrchestratorRun = None
) -> Union[AgentRun, OrchestratorRun]:
    """Loads and validates the input schema for the agent"""
    if agent_run:
        agent_name = agent_run.agent_deployment.module['name'].replace("-", "_")
        schemas_module = importlib.import_module(f"{agent_name}.schemas")
        InputSchema = getattr(schemas_module, "InputSchema")
        agent_run.inputs = InputSchema(**agent_run.inputs)
        return agent_run
    elif orchestrator_run:
        orchestrator_name = orchestrator_run.orchestrator_deployment.module['name']
        tn = orchestrator_name.replace("-", "_")
        schemas_module = importlib.import_module(f"{tn}.schemas")
        InputSchema = getattr(schemas_module, "InputSchema")
        orchestrator_run.inputs = InputSchema(**orchestrator_run.inputs)
        return orchestrator_run
    else:
        raise ValueError("Either agent_run or orchestrator_run must be provided")

async def load_module(run, module_type="agent"):
    """Loads a module (agent or environment) and returns the function and validated run data
    
    Args:
        run: Either AgentRun or EnvironmentRun object
        module_type: String indicating the type ("agent" or "environment")
    
    Returns:
        tuple: (module_func, validated_run)
    """
    # Load the module from the modules directory
    if module_type == "agent":
        module_name = run.agent_deployment.module['name']
        deployment_attr = "agent_deployment"
    else:  # environment
        module_name = run.environment_deployment.module['name']
        deployment_attr = "environment_deployment"

    module_path = Path(f"{AGENTS_SOURCE_DIR}/{module_name}")

    # Load configs
    deployments = await load_agent_deployments(
        module_path / module_name / "configs/agent_deployments.json",
        getattr(run, deployment_attr).module
    )
    deployment = deployments[0]
    setattr(run, deployment_attr, deployment)

    # Handle output configuration
    if deployment.data_generation_config.save_outputs:
        if ':' in run.id:
            output_path = f"{BASE_OUTPUT_DIR}/{run.id.split(':')[1]}"
        else:
            output_path = f"{BASE_OUTPUT_DIR}/{run.id}"
        deployment.data_generation_config.save_outputs_path = output_path
        if not os.path.exists(output_path):
            os.makedirs(output_path)

    run = await load_and_validate_input_schema(run)
    
    # Load the module function
    module_name = module_name.replace("-", "_")
    entrypoint = deployment.module["entrypoint"].split(".")[0]
    main_module = importlib.import_module(f"{module_name}.run")
    main_module = importlib.reload(main_module)
    module_func = getattr(main_module, entrypoint)
    
    return module_func, run

async def load_orchestrator(orchestrator_run, agent_source_dir):
    """Loads the orchestrator and returns the orchestrator function"""
    workflow_name = orchestrator_run.orchestrator_deployment.module['name']
    workflow_path = f"{agent_source_dir}/{workflow_name}"

    # Load the component.yaml file
    # cfg = load_yaml_config(f"{workflow_path}/{workflow_name}/component.yaml")

    # Load configuration JSONs
    config_path = f"{workflow_path}/{workflow_name}/configs"
    with open(f"{config_path}/agent_deployments.json") as f:
        default_agent_deployments = json.load(f)
    with open(f"{config_path}/llm_configs.json") as f:
        llm_configs = {conf["config_name"]: conf for conf in json.load(f)}

    for i, agent_deployment in enumerate(orchestrator_run.agent_deployments):
        if i < len(default_agent_deployments):
            default_config = default_agent_deployments[i]
            
            # Update agent deployment name
            agent_deployment.name = default_config["name"]

            # Update missing module info
            if agent_deployment.module is None:
                agent_deployment.module = default_config["module"]
            
            # Update missing worker_node_url
            if agent_deployment.worker_node_url is None:
                agent_deployment.worker_node_url = default_config["worker_node_url"]
            
            # Update agent config
            if agent_deployment.agent_config is None:
                agent_deployment.agent_config = AgentConfig(**default_config["agent_config"])
            
            # Get LLM config from default config and llm_configs
            if default_config["agent_config"]["llm_config"]["config_name"] in llm_configs:
                llm_config_name = default_config["agent_config"]["llm_config"]["config_name"]
                llm_config = LLMConfig(**llm_configs[llm_config_name])
                agent_deployment.agent_config.llm_config = llm_config
            
            # Update other agent config fields if None
            if agent_deployment.agent_config.persona_module is None:
                agent_deployment.agent_config.persona_module = default_config["agent_config"]["persona_module"]
            
            if agent_deployment.agent_config.system_prompt is None:
                agent_deployment.agent_config.system_prompt = default_config["agent_config"]["system_prompt"]

    validated_data = load_and_validate_input_schema(orchestrator_run)

    # TODO: check if there is dynamic entrypoint
    tn = workflow_name.replace("-", "_")
    entrypoint = 'run'
    main_module = importlib.import_module(f"{tn}.run")
    main_module = importlib.reload(main_module)
    orchestrator_func = getattr(main_module, entrypoint)

    return orchestrator_func, orchestrator_run, validated_data