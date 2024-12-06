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
    EnvironmentDeployment,
    EnvironmentRun,
    OrchestratorRun, 
    LLMConfig, 
    AgentConfig,
    DataGenerationConfig
)
from node.worker.utils import download_from_ipfs, unzip_file, load_yaml_config
from node.config import BASE_OUTPUT_DIR, MODULES_SOURCE_DIR

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
                    raise LockAcquisitionError(f"Failed to acquire lock after {timeout} seconds")
                time.sleep(1)

        yield lock_fd

    finally:
        if lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            lock_fd.close()

def is_module_installed(module_name: str, required_version: str) -> bool:
    try:
        importlib.import_module(module_name)
        modules_source_dir = os.path.join(MODULES_SOURCE_DIR, module_name)

        if not Path(modules_source_dir).exists():
            logger.warning(f"Modules source directory for {module_name} does not exist")
            return False

        try:
            repo = Repo(modules_source_dir)
            if repo.head.is_detached:
                current_tag = next((tag.name for tag in repo.tags if tag.commit == repo.head.commit), None)
            else:
                current_tag = next((tag.name for tag in repo.tags if tag.commit == repo.head.commit),None)

            if current_tag:
                logger.info(f"Module {module_name} is at tag: {current_tag}")
                current_version = (current_tag[1:] if current_tag.startswith("v") else current_tag)
                required_version = (
                    required_version[1:]
                    if required_version.startswith("v")
                    else required_version
                )
                return current_version == required_version
            else:
                logger.warning(f"No tag found for current commit in {module_name}")
                return False
        except (InvalidGitRepositoryError, GitCommandError) as e:
            logger.error(f"Git error for {module_name}: {str(e)}")
            return False

    except ImportError:
        logger.warning(f"Module {module_name} not found")
        return False

async def ensure_module_installation_with_lock(run: Union[AgentRun, EnvironmentRun, OrchestratorRun], run_version: str):
    if isinstance(run, AgentRun):
        module_name = run.agent_deployment.module["name"]
        url = run.agent_deployment.module["url"]    
    elif isinstance(run, OrchestratorRun):
        module_name = run.orchestrator_deployment.module["name"]
        url = run.orchestrator_deployment.module["url"]
    else:  # EnvironmentRun
        module_name = run.environment_deployment.module["name"]
        url = run.environment_deployment.module["url"]

    if module_name in INSTALLED_MODULES:
        installed_version = INSTALLED_MODULES[module_name]
        if installed_version == run_version:
            logger.info(f"Module {module_name} version {run_version} is already installed")
            return True

    lock_file = Path(MODULES_SOURCE_DIR) / f"{module_name}.lock"
    logger.info(f"Lock file: {lock_file}")
    try:
        with file_lock(lock_file):
            logger.info(f"Acquired lock for {module_name}")

            if not is_module_installed(module_name, run_version):
                logger.info(f"Module {module_name} version {run_version} is not installed. Attempting to install...")
                if not url:
                    raise ValueError(f"Module URL is required for installation of {module_name}")
                install_module(module_name, run_version, url)

            # Verify module installation
            if not verify_module_installation(module_name):
                raise RuntimeError(f"Module {module_name} failed verification after installation")

            # Install personas if they exist in module run
            if isinstance(run, AgentRun):
                if hasattr(run, 'personas_urls') and run.agent_deployment.module["personas_urls"]:
                    logger.info(f"Installing personas for agent {module_name}")
                    await install_persona(run.agent_deployment.module["personas_urls"])

            logger.info(f"Module {module_name} version {run_version} is installed and verified")
            INSTALLED_MODULES[module_name] = run_version
    except LockAcquisitionError as e:
        error_msg = f"Failed to acquire lock for module {module_name}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = f"Failed to install or verify module {module_name}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e

def verify_module_installation(module_name: str) -> bool:
    try:
        importlib.import_module(f"{module_name}.run")
        return True
    except ImportError as e:
        logger.error(f"Error importing module {module_name}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    

async def install_persona(personas_url: str):
    if not personas_url:
        logger.info("No personas to install")
        return

    personas_base_dir = Path(MODULES_SOURCE_DIR) / "personas"
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


def install_module_from_ipfs(module_name: str, module_version: str, module_source_url: str):
    logger.info(f"Installing/updating module {module_name} version {module_version}")
    modules_source_dir = Path(MODULES_SOURCE_DIR) / module_name
    logger.info(f"Module path exists: {modules_source_dir.exists()}")
    try:
        module_ipfs_hash = module_source_url.split("ipfs://")[1]
        module_temp_zip_path = download_from_ipfs(module_ipfs_hash, MODULES_SOURCE_DIR)
        unzip_file(module_temp_zip_path, modules_source_dir)
        os.remove(module_temp_zip_path)

    except Exception as e:
        error_msg = f"Error installing {module_name}: {str(e)}"
        logger.error(error_msg)
        logger.info(f"Traceback: {traceback.format_exc()}")
        raise RuntimeError(error_msg) from e


def install_module_from_git(module_name: str, module_version: str, module_source_url: str):
    logger.info(f"Installing/updating module {module_name} version {module_version}")
    modules_source_dir = Path(MODULES_SOURCE_DIR) / module_name
    logger.info(f"Module path exists: {modules_source_dir.exists()}")
    try:
        if modules_source_dir.exists():
            logger.info(f"Updating existing repository for {module_name}")
            repo = Repo(modules_source_dir)
            repo.remotes.origin.fetch()
            repo.git.checkout(module_version)
            logger.info(f"Successfully updated {module_name} to version {module_version}")
        else:
            # Clone new repository
            logger.info(f"Cloning new repository for {module_name}")
            Repo.clone_from(module_source_url, modules_source_dir)
            repo = Repo(modules_source_dir)
            repo.git.checkout(module_version)
            logger.info(f"Successfully cloned {module_name} version {module_version}")

    except Exception as e:
        error_msg = f"Error installing {module_name}: {str(e)}"
        logger.error(error_msg)
        logger.info(f"Traceback: {traceback.format_exc()}")
        if "Dependency conflict detected" in str(e):
            error_msg += "\nThis is likely due to a mismatch in naptha-sdk versions between the module and the main project."
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

def install_module(module_name: str, module_version: str, module_source_url: str):
    logger.info(f"Installing/updating module {module_name} version {module_version}")
    
    modules_source_dir = Path(MODULES_SOURCE_DIR) / module_name
    logger.info(f"Module path exists: {modules_source_dir.exists()}")

    try:
        if "ipfs://" in module_source_url:
            install_module_from_ipfs(module_name, module_version, module_source_url)
        else:
            install_module_from_git(module_name, module_version, module_source_url)
            
        # Reinstall the module
        logger.info(f"Installing/Reinstalling {module_name}")
        installation_output = run_poetry_command(["add", f"{modules_source_dir}"])
        logger.info(f"Installation output: {installation_output}")

        if not verify_module_installation(module_name):
            raise RuntimeError(f"Module {module_name} failed verification after installation")

        logger.info(f"Successfully installed and verified {module_name} version {module_version}")
    except Exception as e:
        error_msg = f"Error installing {module_name}: {str(e)}"
        logger.error(error_msg)
        logger.info(f"Traceback: {traceback.format_exc()}")
        if "Dependency conflict detected" in str(e):
            error_msg += "\nThis is likely due to a mismatch in naptha-sdk versions between the module and the main project."
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


async def load_data_generation_config(agent_run, data_generation_config_path):
    run_config = agent_run.agent_deployment.data_generation_config
    if run_config is None:
        run_config = DataGenerationConfig()

    if isinstance(run_config, DataGenerationConfig):
        run_config = run_config.model_dump()
    
    if os.path.exists(data_generation_config_path):    
        with open(data_generation_config_path, "r") as file:
            file_config = json.loads(file.read())
            if file_config:
                # Start with run config as base
                config_dict = run_config.copy()
                
                # Fill in None values from file config
                for key, run_value in run_config.items():
                    if run_value is None and key in file_config:
                        config_dict[key] = file_config[key]
                        
                return DataGenerationConfig(**config_dict)
    
    # If no file exists or file is empty, use run config
    return agent_run.agent_deployment.data_generation_config

async def load_agent_deployments(agent_run, agent_deployments_path, module):
    with open(agent_deployments_path, "r") as file:
        default_agent_deployments = json.loads(file.read())

    def merge_configs(run_config, default_config):
        """Merge configs with run_config taking precedence"""
        if not run_config:
            return default_config
            
        if isinstance(run_config, dict) and isinstance(default_config, dict):
            result = default_config.copy()  # Start with defaults
            # Override with run_config values that aren't None
            for key, run_value in run_config.items():
                if run_value is not None:
                    if isinstance(run_value, (dict, list)):
                        result[key] = merge_configs(run_value, result.get(key, {}))
                    else:
                        result[key] = run_value
            return result
        return run_config if run_config is not None else default_config

    result_deployments = []
    for default_deployment in default_agent_deployments:
        deployment = default_deployment.copy()
        deployment["module"] = module
        
        # Load LLM config
        if "agent_config" in deployment and "llm_config" in deployment["agent_config"]:
            config_name = deployment["agent_config"]["llm_config"]["config_name"]
            config_path = agent_deployments_path.parent / "llm_configs.json"
            llm_configs = load_llm_configs(config_path)
            llm_config = next(config for config in llm_configs if config.config_name == config_name)
            deployment["agent_config"]["llm_config"] = llm_config.dict()

        # Merge with run configuration
        run_deployment = agent_run.agent_deployment.dict(exclude_unset=True)
        merged_deployment = merge_configs(run_deployment, deployment)

        # Load persona if persona_module url exists
        if "persona_module" in deployment["agent_config"] and "url" in deployment["agent_config"]["persona_module"]:
            persona_dir = await install_persona(deployment["agent_config"]["persona_module"]["url"])
            logger.info(f"Persona directory: {persona_dir}")
            persona_data = load_persona(persona_dir)
            deployment["agent_config"]["persona_module"]["data"] = persona_data
            merged_deployment["agent_config"]["persona_module"]["data"] = persona_data
        
        result_deployments.append(AgentDeployment(**merged_deployment))

    return result_deployments

def load_environment_deployments(environment_deployments_path, module):
    with open(environment_deployments_path, "r") as file:
        environment_deployments = json.loads(file.read())
    for deployment in environment_deployments:
        deployment["module"] = module
        if "environment_config" in deployment and isinstance(deployment["environment_config"], dict):
            # Get the config_schema from environment_config.config_name
            config_schema = deployment["environment_config"].get("config_name", "EnvironmentConfig")
            # Import the specific config class from the module's schemas
            module_name = module["name"].replace("-", "_")
            schemas_module = importlib.import_module(f"{module_name}.schemas")
            ConfigClass = getattr(schemas_module, config_schema)
            # Create instance of the specific config class
            deployment["environment_config"] = ConfigClass(**deployment["environment_config"])
    return [EnvironmentDeployment(**deployment) for deployment in environment_deployments]

async def load_and_validate_input_schema(module_run: Union[AgentRun, OrchestratorRun, EnvironmentRun]) -> Union[AgentRun, OrchestratorRun, EnvironmentRun]:
    if isinstance(module_run, AgentRun):
        module_name = module_run.agent_deployment.module['name']
    elif isinstance(module_run, OrchestratorRun):
        module_name = module_run.orchestrator_deployment.module['name']
    elif isinstance(module_run, EnvironmentRun):
        module_name = module_run.environment_deployment.module['name']
    else:
        raise ValueError("module_run must be either AgentRun, OrchestratorRun, or EnvironmentRun")

    # Replace hyphens with underscores in module name
    module_name = module_name.replace("-", "_")
    
    # Import and validate schema
    schemas_module = importlib.import_module(f"{module_name}.schemas")
    InputSchema = getattr(schemas_module, "InputSchema")
    module_run.inputs = InputSchema(**module_run.inputs)
    
    return module_run

async def load_module(run, module_type="agent"):
    # Load the module from the modules directory
    if module_type == "agent":
        module_name = run.agent_deployment.module['name']
        deployment_attr = "agent_deployment"
        module_path = Path(f"{MODULES_SOURCE_DIR}/{module_name}")
        
        # Load configs
        deployments = await load_agent_deployments(
            agent_run=run,
            agent_deployments_path=module_path / module_name / "configs/agent_deployments.json",
            module=getattr(run, deployment_attr).module
        )
        deployment = deployments[0]
        setattr(run, deployment_attr, deployment)

        # Load data generation config
        data_generation_config = await load_data_generation_config(
            agent_run=run,
            data_generation_config_path=module_path / module_name / "configs/data_generation_config.json"
        )
        run.agent_deployment.data_generation_config = data_generation_config
        
    elif module_type == "environment":
        module_name = run.environment_deployment.module['name']
        deployment_attr = "environment_deployment"
        module_path = Path(f"{MODULES_SOURCE_DIR}/{module_name}")
        
        # Load configs
        deployments = load_environment_deployments(
            environment_deployments_path=module_path / module_name / "configs/environment_deployments.json",
            module=getattr(run, deployment_attr).module
        )
        deployment = deployments[0]
        setattr(run, deployment_attr, deployment)

    else:
        raise ValueError("module_type must be either 'agent' or 'environment'")

    if module_type == "agent" and deployment.data_generation_config:
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
    
    # Load configuration JSONs
    config_path = f"{workflow_path}/{workflow_name}/configs"
    with open(f"{config_path}/agent_deployments.json") as f:
        default_agent_deployments = json.load(f)
    with open(f"{config_path}/llm_configs.json") as f:
        llm_configs = {conf["config_name"]: conf for conf in json.load(f)}

    # Track which default configs have been used
    used_defaults = set()
    
    # Convert list to keep final agent deployments
    final_agent_deployments = []

    # First process incoming agent deployments
    for agent_deployment in orchestrator_run.agent_deployments:
        matched_default = None
        
        # Try to find matching default config by name
        for i, default_config in enumerate(default_agent_deployments):
            if agent_deployment.name == default_config["name"]:
                matched_default = default_config
                used_defaults.add(i)
                break
        
        if matched_default:
            # Use existing agent_deployment but fill in missing fields from default
            if agent_deployment.module is None:
                agent_deployment.module = matched_default["module"]
            if agent_deployment.worker_node_url is None:
                agent_deployment.worker_node_url = matched_default["worker_node_url"]
            
            # Handle agent_config
            if agent_deployment.agent_config is None:
                agent_deployment.agent_config = AgentConfig(**matched_default["agent_config"])
            else:
                default_agent_config = matched_default["agent_config"]
                for key, value in default_agent_config.items():
                    if not hasattr(agent_deployment.agent_config, key) or getattr(agent_deployment.agent_config, key) is None:
                        setattr(agent_deployment.agent_config, key, value)
            
            # Handle LLM config
            llm_config_name = matched_default["agent_config"]["llm_config"]["config_name"]
            if llm_config_name in llm_configs and agent_deployment.agent_config.llm_config is None:
                agent_deployment.agent_config.llm_config = LLMConfig(**llm_configs[llm_config_name])
            
            final_agent_deployments.append(agent_deployment)

    # Add any unused default configurations
    for i, default_config in enumerate(default_agent_deployments):
        if i not in used_defaults:
            # Create new agent deployment from default config
            agent_config = AgentConfig(**default_config["agent_config"])
            
            # Set LLM config
            llm_config_name = default_config["agent_config"]["llm_config"]["config_name"]
            if llm_config_name in llm_configs:
                agent_config.llm_config = LLMConfig(**llm_configs[llm_config_name])
            
            new_deployment = AgentDeployment(
                name=default_config["name"],
                module=default_config["module"],
                worker_node_url=default_config["worker_node_url"],
                agent_config=agent_config
            )
            final_agent_deployments.append(new_deployment)

    # Replace worker_node_url if it exists in incoming orchestrator_run
    for i, deployment in enumerate(final_agent_deployments):
        incoming_deployment = orchestrator_run.agent_deployments[i]
        if incoming_deployment.worker_node_url:
            deployment.worker_node_url = incoming_deployment.worker_node_url

    # Update orchestrator_run with final deployments
    orchestrator_run.agent_deployments = final_agent_deployments

    # Validate the input schema
    validated_data = load_and_validate_input_schema(orchestrator_run)

    # Import and reload the orchestrator module
    tn = workflow_name.replace("-", "_")
    entrypoint = 'run'
    main_module = importlib.import_module(f"{tn}.run")
    main_module = importlib.reload(main_module)
    orchestrator_func = getattr(main_module, entrypoint)

    logger.info(f"Orchestrator run x2: {orchestrator_run}")

    return orchestrator_func, orchestrator_run, validated_data
