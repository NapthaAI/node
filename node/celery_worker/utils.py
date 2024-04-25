import os
import zipfile
import tempfile
import ipfshttpclient
from dotenv import load_dotenv
from pathlib import Path
from node.utils import get_logger


load_dotenv()
logger = get_logger(__name__)


BASE_ROOT_DIR = os.getcwd()
FILE_PATH = Path(__file__).resolve()
CELERY_WORKER_DIR = FILE_PATH.parent
NODE_DIR = CELERY_WORKER_DIR.parent
MODULES_PATH = f"{NODE_DIR}/{os.getenv('MODULES_PATH')}"
BASE_OUTPUT_DIR = os.getenv("BASE_OUTPUT_DIR")
BASE_OUTPUT_DIR = NODE_DIR / BASE_OUTPUT_DIR[2:]


def download_from_ipfs(ipfs_hash: str, temp_dir: str) -> str:
    """Download content from IPFS to a given temporary directory."""
    IPFS_GATEWAY_URL = os.getenv("IPFS_GATEWAY_URL", None)
    if not IPFS_GATEWAY_URL:
        raise Exception("IPFS_GATEWAY_URL is not set in the environment")
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
    except Exception as e:
        logger.info(f"File is not a zip file: {downloaded_path}")

    return temp_dir


def upload_to_ipfs(input_dir: str) -> str:
    """Upload a file or directory to IPFS. And pin it."""
    logger.info(f"Uploading to IPFS: {input_dir}")
    IPFS_GATEWAY_URL = os.getenv("IPFS_GATEWAY_URL", None)
    if not IPFS_GATEWAY_URL:
        raise Exception("IPFS_GATEWAY_URL is not set in the environment")
    client = ipfshttpclient.connect(IPFS_GATEWAY_URL)
    res = client.add(input_dir, recursive=True)
    logger.info(f"IPFS add response: {res}")
    ipfs_hash = res[-1]["Hash"]
    client.pin.add(ipfs_hash)
    return ipfs_hash
