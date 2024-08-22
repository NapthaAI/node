from git import Repo
import json
import os
from pathlib import Path
import shutil
from node.utils import run_subprocess
from node.utils import get_logger, get_config

logger = get_logger(__name__)

PARENT_DIR = Path(__file__).resolve().parent
MODULES_PATH = f"{get_config()['MODULES_PATH']}"
MODULES_PATH = os.path.join(str(PARENT_DIR), MODULES_PATH)
logger.info(f"MODULES_PATH: {MODULES_PATH}")


def clone_repo(
    tag,
    module_name,
    url="https://github.com/moarshy/daimon-templates",
    clone_dir=MODULES_PATH,
):
    logger.info(f"Cloning repo {url} with tag {tag} to {clone_dir}")
    repo_path = Path(clone_dir) / module_name
    repo = Repo.clone_from(url, repo_path)
    logger.info(f"Checking out tag {tag}")
    repo.git.checkout(tag)
    logger.info(f"Done cloning repo {url} with tag {tag} to {clone_dir}")


def install_module(template_name, modules_path=MODULES_PATH):
    # Get the path to the template
    template_path = f"{modules_path}/{template_name}"

    # resolve to full path
    template_path = os.path.abspath(template_path)
    logger.info(f"Installing module {template_name} from {template_path}")

    # Use subprocess to add the template to the poetry environment
    run_subprocess(["poetry", "add", f"{template_path}"])

    # Use subprocess to install the template dependencies
    run_subprocess(["poetry", "install"])


def setup_modules_from_config(module_config_path):
    logger.info(f"Downloading AI modules in {module_config_path}")
    # Make sure the modules directory is empty
    if os.path.exists(MODULES_PATH):
        shutil.rmtree(MODULES_PATH)
    with open(module_config_path) as f:
        modules_config_file = json.load(f)

    for package, url in modules_config_file.items():
        # Download the module
        parts = package.split("/")
        package_name = parts[1]
        tag = "v" + package.split("/")[-1]
        try:
            clone_repo(tag=tag, url=url, module_name=package_name)
        except Exception as e:
            logger.error(f"Failed to clone repo: {e}")
            raise e

        # Install the module
        try:
            install_module(package_name)
        except Exception as e:
            logger.error(f"Failed to install module: {e}")
            raise e

    logger.info(f"Done downloading and installing AI modules in {module_config_path}")