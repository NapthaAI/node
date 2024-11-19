import os
import zipfile
import tempfile
import ipfshttpclient
from dotenv import load_dotenv
from pathlib import Path
from node.schemas import AgentRun, OrchestratorRun
from node.config import BASE_OUTPUT_DIR, IPFS_GATEWAY_URL
from node.storage.db.db import DB
from typing import Dict, Optional
import logging
import yaml
from websockets.exceptions import ConnectionClosedError
import asyncio
from functools import wraps

from node.storage.storage import get_ipns_record

load_dotenv()
logger = logging.getLogger(__name__)


MAX_RETRIES = 3
RETRY_DELAY = 1


def download_from_ipfs(ipfs_hash: str, temp_dir: str) -> str:
    """Download content from IPFS to a given temporary directory."""
    client = ipfshttpclient.connect(IPFS_GATEWAY_URL)
    client.get(ipfs_hash, target=temp_dir)
    return os.path.join(temp_dir, ipfs_hash)


def unzip_file(zip_path: Path, extract_dir: Path) -> None:
    """Unzip a zip file to a specified directory."""
    logger.info(f"Unzipping file: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)


def handle_ipfs_input(ipfs_hash: str) -> str:
    """
    Download input from IPFS, unzip if necessary, delete the .zip, and return the path to the input directory.
    """
    logger.info(f"Downloading from IPFS: {ipfs_hash}")
    temp_dir = tempfile.mkdtemp()
    downloaded_path = download_from_ipfs(ipfs_hash, temp_dir)

    #  try to unzip the downloaded file
    try:
        unzip_file(Path(downloaded_path), Path(temp_dir))
        os.remove(downloaded_path)
        logger.info(f"Unzipped file: {downloaded_path}")
    except Exception:
        logger.info(f"File is not a zip file: {downloaded_path}")
    if os.path.isdir(os.path.join(temp_dir, ipfs_hash)):
        return os.path.join(temp_dir, ipfs_hash)
    else:
        return temp_dir


def upload_to_ipfs(input_dir: str) -> str:
    """Upload a file or directory to IPFS. And pin it."""
    logger.info(f"Uploading to IPFS: {input_dir}")
    client = ipfshttpclient.connect(IPFS_GATEWAY_URL)
    res = client.add(input_dir, recursive=True)
    logger.info(f"IPFS add response: {res}")
    ipfs_hash = res[-1]["Hash"]
    client.pin.add(ipfs_hash)
    return ipfs_hash


def upload_json_string_to_ipfs(json_string: str) -> str:
    """Upload a json string to IPFS. And pin it."""
    logger.info("Uploading json string to IPFS")
    client = ipfshttpclient.connect(IPFS_GATEWAY_URL)
    res = client.add_str(json_string)
    logger.info(f"IPFS add response: {res}")
    client.pin.add(res)
    return res


def with_retry(max_retries=MAX_RETRIES, delay=RETRY_DELAY):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except ConnectionClosedError as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Max retries reached. Last error: {str(e)}")
                        raise
                    logger.warning(
                        f"Connection closed. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)

        return wrapper

    return decorator


@with_retry()
async def update_db_with_status_sync(
    agent_run: AgentRun = None, 
    orchestrator_run: OrchestratorRun = None
) -> None:
    """
    Update the DB with the agent run status synchronously
    param agent_run: AgentRun data to update
    """
    logger.info("Updating DB with agent run")

    try:
        if agent_run:
            async with DB() as db:
                updated_agent_run = await db.update_agent_run(agent_run.id, agent_run)
                logger.info(f"Updated agent run: {updated_agent_run}")
        elif orchestrator_run:
            async with DB() as db:
                updated_orchestrator_run = await db.update_orchestrator_run(orchestrator_run.id, orchestrator_run)
                logger.info(f"Updated orchestrator run: {updated_orchestrator_run}")
        else:
            logger.error("Either agent_run or orchestrator_run must be provided")
            raise ValueError("Either agent_run or orchestrator_run must be provided")
    except ConnectionClosedError:
        # This will be caught by the retry decorator
        raise
    except Exception as e:
        logger.error(f"Failed to update DB with agent run status: {str(e)}")
        raise


def load_yaml_config(cfg_path):
    with open(cfg_path, "r") as file:
        return yaml.load(file, Loader=yaml.FullLoader)


def prepare_input_dir(
    parameters: Dict,
    input_dir: Optional[str] = None,
    input_ipfs_hash: Optional[str] = None,
):
    """Prepare the input directory"""
    # make sure only input_dir or input_ipfs_hash is present
    if input_dir and input_ipfs_hash:
        raise ValueError("Only one of input_dir or input_ipfs_hash can be provided")

    if input_dir:
        input_dir = f"{BASE_OUTPUT_DIR}/{input_dir}"
        parameters["input_dir"] = input_dir

        if not os.path.exists(input_dir):
            raise ValueError(f"Input directory {input_dir} does not exist")

    if input_ipfs_hash:
        if input_ipfs_hash.startswith("k"):
            ipfs_hash = get_ipns_record(input_ipfs_hash)
        else:
            ipfs_hash = input_ipfs_hash

        input_dir = handle_ipfs_input(ipfs_hash)
        parameters["input_dir"] = input_dir

    return parameters
