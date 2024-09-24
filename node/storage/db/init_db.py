from dotenv import load_dotenv
from node.config import BASE_OUTPUT_DIR, DB_NS, DB_DB, SURREALDB_PORT
from node.agent_manager import install_agents_from_config
from node.utils import create_output_dir, get_logger
import os
from pathlib import Path
import subprocess
import time

load_dotenv()
logger = get_logger(__name__)

file_path = Path(__file__).resolve().parent
local_db_file_path = f"{file_path}/db.db"
surql_path = f"{file_path}/data_structures"
root_dir = file_path.parent.parent

logger.info(f"DB root pass: {os.getenv('DB_ROOT_PASS')}")
logger.info(f"DB root user: {os.getenv('DB_ROOT_USER')}")


def import_surql():
    """Import SURQL files to the database"""
    logger.info("Importing SURQL files")
    import_files = [
        f"{surql_path}/user.surql",
        f"{surql_path}/agent_run.surql",
        f"{surql_path}/auth.surql",
    ]

    for file in import_files:
        command = f"""surreal import \
                      --conn http://localhost:{SURREALDB_PORT} \
                      --user {os.getenv('DB_ROOT_USER')} \
                      --pass {os.getenv('DB_ROOT_PASS')} \
                      --ns {DB_NS} \
                      --db {DB_DB} \
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

    # use file storage
    command = f"""surreal start -A --auth \
                  --user {os.getenv('DB_ROOT_USER')} \
                  --bind 0.0.0.0:{SURREALDB_PORT} \
                  --pass {os.getenv('DB_ROOT_PASS')} \
                  file:{local_db_file_path}"""

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
    install_agents_from_config(Path(f"{root_dir}/storage/hub/packages.json"))


if __name__ == "__main__":
    init_db()
