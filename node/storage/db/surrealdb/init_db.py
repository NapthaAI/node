from dotenv import load_dotenv
from node.config import BASE_OUTPUT_DIR, HUB_NS, HUB_DB, HUB_DB_PORT, HUB_HOSTNAME
from node.utils import create_output_dir
import os
import logging
from pathlib import Path
import subprocess
import time

load_dotenv()
logger = logging.getLogger(__name__)

file_path = Path(__file__).resolve().parent
local_db_file_path = f"{file_path}/db.db"
surql_path = f"{file_path}/data_structures"
root_dir = file_path.parent.parent

def import_surql():
    """Import SURQL files to the database"""
    logger.info("Importing SURQL files")
    logger.info(f"DB root pass: {os.getenv('HUB_ROOT_USER')}")
    logger.info(f"DB root user: {os.getenv('HUB_ROOT_PASS')}")

    import_files = [
        f"{surql_path}/user.surql",
        f"{surql_path}/agent_run.surql",
        f"{surql_path}/auth.surql",
    ]

    for file in import_files:
        command = f"""surreal import \
                      --conn http://{HUB_HOSTNAME}:{HUB_DB_PORT} \
                      --user {os.getenv('HUB_ROOT_USER')} \
                      --pass {os.getenv('HUB_ROOT_PASS')} \
                      --ns {HUB_NS} \
                      --db {HUB_DB} \
                    {file}"""

        try:
            logger.info(f"Importing {file.rsplit('/', 1)[-1]}")
            process = subprocess.Popen(
                command,
                shell=True,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
            )
            out, err = process.communicate()
            logger.info(out)
            logger.info(err)
        except Exception as e:
            logger.error("Error creating scope")
            logger.error(str(e))
            raise


def init_db():
    """Initialize the database"""
    logger.info("Initializing database")

    command = f""" surreal isready --conn http://{HUB_HOSTNAME}:{HUB_DB_PORT}"""

    try:
        # Start the command in a new process and detach it
        _ = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            preexec_fn=os.setsid,
        )
        logger.info("Database initialization command executed")
    except Exception as e:
        logger.error("Error initializing database")
        logger.error(str(e))
        raise

    time.sleep(5)
    logger.info("Database initialized")
    import_surql()

    create_output_dir(BASE_OUTPUT_DIR)


if __name__ == "__main__":
    init_db()
