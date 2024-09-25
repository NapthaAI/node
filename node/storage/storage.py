import os
import io
from node.config import BASE_OUTPUT_DIR, IPFS_GATEWAY_URL
from node.utils import get_logger
from uuid import uuid4
from pathlib import Path
import ipfshttpclient
import zipfile
import shutil
import requests
import tempfile

logger = get_logger(__name__)


def zip_dir(directory_path: str) -> io.BytesIO:
    """
    Zip the specified directory and return a BytesIO object containing the zip file.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                zip_file.write(file_path, os.path.relpath(file_path, directory_path))
    zip_buffer.seek(0)
    return zip_buffer


async def write_storage(file):
    """Write files to the storage."""
    logger.info(f"Received request to write files to storage: {file.filename}")
    folder_name = uuid4().hex
    folder_path = Path(BASE_OUTPUT_DIR) / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    temp_file_path = folder_path / file.filename

    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if file.filename.endswith(".zip"):
        with zipfile.ZipFile(temp_file_path, "r") as zip_ref:
            zip_ref.extractall(folder_path)

        # delete zip file
        os.remove(temp_file_path)
    else:
        pass

    return (201, {"message": "Files written to storage", "folder_id": folder_name})


def zip_directory(file_path, zip_path):
    """Utility function to recursively zip the content of a directory and its subdirectories, 
    placing the contents in the zip as if the provided file_path was the root."""
    base_path_len = len(Path(file_path).parts)  # Number of path segments in the base path
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(file_path):
            for file in files:
                full_path = os.path.join(root, file)
                # Generate the archive name by stripping the base_path part
                arcname = os.path.join(*Path(full_path).parts[base_path_len:])
                zipf.write(full_path, arcname)


async def read_storage(job_id: str):
    """Get the output directory for a job_id and serve it as a tar.gz file."""
    logger.info(f"Received request for output dir for job: {job_id}")
    if ":" in job_id:
        job_id = job_id.split(":")[1]

    job_id = job_id.strip()

    output_path = Path(BASE_OUTPUT_DIR) / job_id
    logger.info(f"Output directory: {output_path}")

    if not output_path.exists():
        logger.error(f"Output directory not found for job: {job_id}")
        return (404, {"message": "Output directory not found"})

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmpfile:
        zip_directory(output_path, tmpfile.name)
        tmpfile.close()

        return (200, {
            "path": tmpfile.name,
            "media_type": "application/zip",
            "filename": f"{job_id}.zip",
            "headers": {"Content-Disposition": f"attachment; filename={job_id}.zip"}
        })


def get_api_url():
    domain = IPFS_GATEWAY_URL.split('/')[2]
    port = IPFS_GATEWAY_URL.split('/')[4]
    return f'http://{domain}:{port}/api/v0'


async def write_to_ipfs(file, publish_to_ipns=False, update_ipns_name=None):
    """Write a file to IPFS, optionally publish to IPNS or update an existing IPNS record."""
    try:
        logger.info(f"Writing file to IPFS: {file.filename}")
        if not IPFS_GATEWAY_URL:
            return (500, {"message": "IPFS_GATEWAY_URL not found in environment"})
        
        client = ipfshttpclient.connect(IPFS_GATEWAY_URL)
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmpfile:
            content = await file.read()
            tmpfile.write(content)
            tmpfile_name = tmpfile.name
        file.file.close()
        
        result = client.add(tmpfile_name)
        client.pin.add(result["Hash"])
        os.unlink(tmpfile_name)
        
        ipfs_hash = result["Hash"]
        response = {
            "message": "File written and pinned to IPFS",
            "ipfs_hash": ipfs_hash,
        }

        if publish_to_ipns:
            ipns_hash = publish_to_ipns_func(ipfs_hash)
            response["ipns_hash"] = ipns_hash
            response["message"] += " and published to IPNS"
        elif update_ipns_name:
            updated_ipns_hash = update_ipns_record(update_ipns_name, ipfs_hash)
            response["ipns_hash"] = updated_ipns_hash
            response["message"] += " and IPNS record updated"

        return (201, response)
    except Exception as e:
        logger.error(f"Error writing file to IPFS: {e}")
        return (500, {"message": f"Error writing file to IPFS: {e}"})


async def read_from_ipfs_or_ipns(hash_or_name: str):
    """Read a file from IPFS or IPNS."""
    try:
        logger.info(f"Reading from IPFS/IPNS: {hash_or_name}")
        if not IPFS_GATEWAY_URL:
            return (500, {"message": "IPFS_GATEWAY_URL not found in environment"})

        # If it's an IPNS name, resolve it to an IPFS hash
        if hash_or_name.startswith('k'):
            ipfs_hash = get_ipns_record(hash_or_name)
        else:
            ipfs_hash = hash_or_name

        client = ipfshttpclient.connect(IPFS_GATEWAY_URL)
        temp_dir = tempfile.mkdtemp()
        client.get(ipfs_hash, target=temp_dir)
        file_path = os.path.join(temp_dir, ipfs_hash)

        if os.path.isdir(file_path):
            zip_buffer = zip_dir(file_path)
            return (200, {
                "content": zip_buffer.getvalue(),
                "media_type": "application/zip",
                "headers": {
                    "Content-Disposition": f"attachment; filename={ipfs_hash}.zip"
                },
            })
        else:
            return (200, {
                "path": file_path,
                "media_type": "application/octet-stream",
                "filename": os.path.basename(file_path),
                "headers": {
                    "Content-Disposition": f"attachment; filename={os.path.basename(file_path)}"
                },
            })
    except Exception as e:
        logger.error(f"Error reading from IPFS/IPNS: {e}")
        return (500, {"message": f"Error reading from IPFS/IPNS: {e}"})


def publish_to_ipns_func(ipfs_hash: str) -> str:
    api_url = get_api_url()
    params = {'arg': ipfs_hash, 'lifetime': '876000h'}  # Set lifetime to infinity (100 years)
    ipns_pub = requests.post(f'{api_url}/name/publish', params=params)
    return ipns_pub.json()['Name']


def get_ipns_record(ipns_name: str) -> str:
    api_url = get_api_url()
    params = {'arg': ipns_name}
    ipns_get = requests.post(f'{api_url}/name/resolve', params=params)
    return ipns_get.json()['Path'].split('/')[-1]


def update_ipns_record(ipns_name: str, ipfs_hash: str) -> str:
    api_url = get_api_url()
    params = {'arg': ipfs_hash, 'key': ipns_name, 'lifetime': '876000h'}  # Set lifetime to infinity (100 years)
    ipns_pub = requests.post(f'{api_url}/name/publish', params=params)
    return ipns_pub.json()['Name']
