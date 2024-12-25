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
from pydantic import BaseModel
from typing import Union, Dict
from node.schemas import (
    AgentDeployment, 
    AgentRun, 
    EnvironmentDeployment,
    EnvironmentRun,
    OrchestratorRun, 
    LLMConfig, 
    AgentConfig,
    DataGenerationConfig,
    KBRun,
    KBDeployment,
    ToolRun,
    ToolDeployment,
    Module,
    AgentModule
)
from node.worker.utils import download_from_ipfs, unzip_file
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

async def install_module_with_lock(module: Union[Dict, AgentModule, Module]):
    if isinstance(module, dict):
        module_name = module["name"]
        url = module["module_url"]
        run_version = module["module_version"]
    else:
        module_name = module.name
        url = module.module_url
        run_version = module.module_version

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
            if isinstance(module, AgentModule):
                if hasattr(module, 'personas_urls') and module.personas_urls:
                    logger.info(f"Installing personas for agent {module_name}")
                    await install_persona(module.personas_urls)

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
        return {"name": module_name, "module_version": module_version, "status": "success"}

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
    run_config = agent_run.deployment.data_generation_config
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
    return agent_run.deployment.data_generation_config

def merge_config(input_config, default_config):
    """
    Deep merge configurations, with input taking precedence over defaults
    
    Args:
        input_config: User provided configuration
        default_config: Default configuration from file
    """
    if not input_config:
        return default_config
        
    if isinstance(input_config, dict) and isinstance(default_config, dict):
        result = default_config.copy()
        for key, input_value in input_config.items():
            if input_value is not None:
                if isinstance(input_value, (dict, list)):
                    result[key] = merge_config(input_value, result.get(key, {}))
                else:
                    result[key] = input_value
        return result
    return input_config if input_config is not None else default_config


async def load_agent_deployments(input_deployments, default_config_path):
    # Load default configurations from file
    with open(default_config_path, "r") as file:
        default_agent_deployments = json.loads(file.read())

    module_path = Path(default_config_path).parent.parent

    for deployment in default_agent_deployments:
        for field, value in deployment.items():
            print(f"  {field}:", value)

    # Load LLM configs for all default deployments
    for deployment in default_agent_deployments:
        if "agent_config" in deployment and "llm_config" in deployment["agent_config"]:
            config_name = deployment["agent_config"]["llm_config"]["config_name"]
            config_path = f"{module_path}/configs/llm_configs.json"
            llm_configs = load_llm_configs(config_path)
            llm_config = next(config for config in llm_configs if config.config_name == config_name)
            deployment["agent_config"]["llm_config"] = llm_config
        if "persona_module" in deployment["agent_config"] and "module_url" in deployment["agent_config"]["persona_module"]:
            persona_url = deployment["agent_config"]["persona_module"]["module_url"]
            persona_dir = await install_persona(persona_url)
            deployment["agent_config"]["persona_module"]["data"] = load_persona(persona_dir)

    result_deployments = []

    # Process each input deployment, merging with defaults
    for i, input_deployment in enumerate(input_deployments):
        # Get corresponding default deployment or use first default if no match
        default_deployment = default_agent_deployments[min(i, len(default_agent_deployments)-1)].copy()

        # Update defaults with non-None values from input
        for key, value in input_deployment.dict(exclude_unset=True).items():           
            if value is not None:
                default_deployment[key] = value

        result_deployments.append(AgentDeployment(**default_deployment))

    for deployment in result_deployments:
        for field, value in deployment.__dict__.items():
            print(f"  {field}:", value)


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

async def load_and_validate_input_schema(module_run: Union[AgentRun, OrchestratorRun, EnvironmentRun, KBRun, ToolRun]) -> Union[AgentRun, OrchestratorRun, EnvironmentRun, KBRun, ToolRun]:
    module_name = module_run.deployment.module['name']

    # Replace hyphens with underscores in module name
    module_name = module_name.replace("-", "_")
    
    # Import and validate schema
    schemas_module = importlib.import_module(f"{module_name}.schemas")
    InputSchema = getattr(schemas_module, "InputSchema")

    module_run.inputs = InputSchema(**module_run.inputs)
    
    return module_run


async def load_kb_deployments(default_kb_deployments_path, input_kb_deployments):
    # Load default configurations from file
    with open(default_kb_deployments_path, "r") as file:
        default_kb_deployments = json.loads(file.read())

    default_kb_deployment = default_kb_deployments[0]
    input_kb_deployment = input_kb_deployments[0]

    # Update defaults with non-None values from input
    for key, value in input_kb_deployment.dict(exclude_unset=True).items():           
        if value is not None:
            default_kb_deployment[key] = value

    return [KBDeployment(**default_kb_deployment)]

async def load_tool_deployments(default_tool_deployments_path, input_tool_deployments):
    # Load default configurations from file
    with open(default_tool_deployments_path, "r") as file:
        default_tool_deployments = json.loads(file.read())

    module_path = Path(default_tool_deployments_path).parent.parent

    for deployment in default_tool_deployments:
        # Load LLM config if present
        if "tool_config" in deployment and "llm_config" in deployment["tool_config"]:
            config_name = deployment["tool_config"]["llm_config"]["config_name"]
            config_path = f"{module_path}/configs/llm_configs.json"
            llm_configs = load_llm_configs(config_path)
            llm_config = next(config for config in llm_configs if config.config_name == config_name)
            deployment["tool_config"]["llm_config"] = llm_config

    default_tool_deployment = default_tool_deployments[0]
    input_tool_deployment = input_tool_deployments[0]

    # Update defaults with non-None values from input
    for key, value in input_tool_deployment.dict(exclude_unset=True).items():           
        if value is not None:
            default_tool_deployment[key] = value

    return [ToolDeployment(**default_tool_deployment)]

async def load_module(module_run, module_type="agent"):

    module_name = module_run.deployment.module['name']
    module_path = Path(f"{MODULES_SOURCE_DIR}/{module_name}/{module_name}")

    # Load sub-deployments
    if hasattr(module_run.deployment, "agent_deployments") and module_run.deployment.agent_deployments:
        agent_deployments = await load_agent_deployments(
            input_deployments=module_run.deployment.agent_deployments,
            default_config_path=module_path / "configs/agent_deployments.json"
        )
        module_run.deployment.agent_deployments = agent_deployments
    if hasattr(module_run.deployment, "tool_deployments") and module_run.deployment.tool_deployments:
        tool_deployments = await load_tool_deployments(
            default_tool_deployments_path=module_path / "configs/tool_deployments.json",
            input_tool_deployments=module_run.deployment.tool_deployments
        )
        module_run.deployment.tool_deployments = tool_deployments
    if hasattr(module_run.deployment, "environment_deployments") and module_run.deployment.environment_deployments:
        environment_deployments = await load_environment_deployments(
            environment_deployments_path=module_path / "configs/environment_deployments.json",
            module=module_run.deployment.module
        )
        module_run.deployment.environment_deployments = environment_deployments
    if hasattr(module_run.deployment, "kb_deployments") and module_run.deployment.kb_deployments:
        kb_deployments = await load_kb_deployments(
            default_kb_deployments_path=module_path / "configs/kb_deployments.json",
            input_kb_deployments=module_run.deployment.kb_deployments
        )
        module_run.deployment.kb_deployments = kb_deployments

    # Load the module from the modules directory
    if module_type == "agent":
        deployments = await load_agent_deployments(
            input_deployments=[module_run.deployment],
            default_config_path=module_path / "configs/agent_deployments.json"
        )
        module_run.deployment = deployments[0]

    elif module_type == "tool":
        tool_deployments = await load_tool_deployments(
            default_tool_deployments_path=module_path / "configs/tool_deployments.json",
            input_tool_deployments=[module_run.deployment]
        )
        module_run.deployment = tool_deployments[0]
        
    elif module_type == "environment":       
        deployments = load_environment_deployments(
            environment_deployments_path=module_path / "configs/environment_deployments.json",
            module=module_run.deployment.module
        )
        module_run.deployment = deployments[0]

    elif module_type == "knowledge_base":
        kb_deployments = await load_kb_deployments(
            default_kb_deployments_path=module_path / "configs/kb_deployments.json",
            input_kb_deployments=[module_run.deployment]
        )
        module_run.deployment = kb_deployments[0]

    else:
        raise ValueError("module_type must be either 'agent', 'tool', 'environment' or 'knowledge_base'")

    if module_type == "agent" and module_run.deployment.data_generation_config:
        # Handle output configuration
        if module_run.deployment.data_generation_config.save_outputs:
            if ':' in module_run.id:
                output_path = f"{BASE_OUTPUT_DIR}/{module_run.id.split(':')[1]}"
            else:
                output_path = f"{BASE_OUTPUT_DIR}/{module_run.id}"
            module_run.deployment.data_generation_config.save_outputs_path = output_path
            if not os.path.exists(output_path):
                os.makedirs(output_path)

    module_run = await load_and_validate_input_schema(module_run)
    
    # Load the module function
    module_name = module_name.replace("-", "_")
    entrypoint = module_run.deployment.module["module_entrypoint"].split(".")[0]
    main_module = importlib.import_module(f"{module_name}.run")
    main_module = importlib.reload(main_module)
    module_func = getattr(main_module, entrypoint)
    
    return module_func, module_run


async def load_orchestrator_deployments(orchestrator_run, agent_source_dir: str):
    """
    Load orchestrator function and prepare run configuration
    """
    workflow_name = orchestrator_run.deployment.module['name']
    config_path = f"{agent_source_dir}/{workflow_name}/{workflow_name}/configs/agent_deployments.json"
    
    # Load and merge deployments using the same function as agents
    deployments = await load_agent_deployments(
        orchestrator_run.deployment.agent_deployments, 
        config_path
    )
    
    # Handle worker_node overrides
    for i, deployment in enumerate(deployments):
        if i < len(orchestrator_run.deployment.agent_deployments):
            incoming_deployment = orchestrator_run.deployment.agent_deployments[i]
            if incoming_deployment.worker_node:
                deployment.worker_node = incoming_deployment.worker_node
    
    # Update orchestrator run and validate
    orchestrator_run.deployment.agent_deployments = deployments
    validated_data = await load_and_validate_input_schema(orchestrator_run)

    # Load orchestrator function
    module_name = workflow_name.replace("-", "_")
    main_module = importlib.reload(importlib.import_module(f"{module_name}.run"))
    orchestrator_func = getattr(main_module, "run")

    return orchestrator_func, orchestrator_run, validated_data


# generic function to load deployments and merge with input deployments
async def load_deployments(deployments_path, input_deployments, deployment_type):
    logger.info(f"deployments_path: {deployments_path}")
    logger.info(f"input_deployments: {input_deployments}")
    logger.info(f"deployment_type: {deployment_type}")
    deployment_map = {
        "agent": AgentDeployment,
        "tool": ToolDeployment,
        "environment": EnvironmentDeployment,
        "kb": KBDeployment
    }

    # Load defaults if file exists
    default_deployments = (
        [deployment_map[deployment_type]().model_dump()] 
        if not os.path.exists(deployments_path)
        else json.load(open(deployments_path))
    )

    logger.info(f"input_deployments: {input_deployments}")

    # Handle empty or None input_deployments
    if not input_deployments:  # This handles both None and empty list
        input_deployments = [deployment_map[deployment_type]()]
        logger.info(f"No input deployments provided, using empty {deployment_type} deployment: {input_deployments[0]}")

    # Always use the first default deployment as base
    merged = merge_config(
        input_deployments[0].dict(exclude_unset=True) if isinstance(input_deployments[0], BaseModel) else input_deployments[0],
        default_deployments[0]
    )
    
    return [deployment_map[deployment_type](**merged)]