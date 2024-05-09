import subprocess
from typing import List
from node.utils import get_logger

logger = get_logger(__name__)


def run_subprocess(cmd: List) -> None:
    """Run a subprocess"""
    logger.info(f"Running subprocess: {cmd}")
    try:
        out, err = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ).communicate()

        # Log the output
        logger.info(f"Subprocess output: {out.decode('utf-8')}")

        if err:
            logger.info(f"Subprocess error: {err.decode('utf-8')}")
            raise Exception(err)

        return out.decode("utf-8")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise e
