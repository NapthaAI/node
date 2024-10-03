import asyncio
from datetime import datetime
import os
import subprocess
from dotenv import load_dotenv, find_dotenv

from node.config import HUB_DB_PORT, HUB_NS, HUB_DB
from node.utils import get_logger

load_dotenv(find_dotenv(), override=True)
logger = get_logger(__name__)

file_path = os.path.dirname(os.path.realpath(__file__))
export_path = os.path.join(file_path, "data_structures")

async def export_surql():
    """Export SURQL data from the database"""
    logger.info("Exporting SURQL data")

    # Create filename with current timestamp
    timestamp = datetime.now().strftime("%d_%m_%Y_%H_%M")
    export_file = f"export_{timestamp}.surql"
    export_full_path = os.path.join(export_path, export_file)

    command = f"""surreal export \
                  --conn http://localhost:{HUB_DB_PORT} \
                  --user {os.getenv('HUB_ROOT_USER')} \
                  --pass {os.getenv('HUB_ROOT_PASS')} \
                  --ns {HUB_NS} \
                  --db {HUB_DB} \
                  {export_full_path}"""

    try:
        logger.info(f"Exporting to {export_file}")
        process = subprocess.Popen(
            command,
            shell=True,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        out, err = process.communicate()
        logger.info(out)
        if err:
            logger.error(err)
        else:
            logger.info(f"Export completed successfully: {export_full_path}")
    except Exception as e:
        logger.error("Error exporting data")
        logger.error(str(e))
        raise

if __name__ == "__main__":
    asyncio.run(export_surql())