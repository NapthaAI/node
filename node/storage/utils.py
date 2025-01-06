import os
import zipfile
from pathlib import Path
import io
from node.config import IPFS_GATEWAY_URL

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


def zip_directory(file_path, zip_path):
    """Utility function to recursively zip the content of a directory and its subdirectories,
    placing the contents in the zip as if the provided file_path was the root."""
    base_path_len = len(
        Path(file_path).parts
    )  # Number of path segments in the base path
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(file_path):
            for file in files:
                full_path = os.path.join(root, file)
                # Generate the archive name by stripping the base_path part
                arcname = os.path.join(*Path(full_path).parts[base_path_len:])
                zipf.write(full_path, arcname)


def get_api_url():
    domain = IPFS_GATEWAY_URL.split("/")[2]
    port = IPFS_GATEWAY_URL.split("/")[4]
    return f"http://{domain}:{port}/api/v0"
