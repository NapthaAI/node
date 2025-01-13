from dotenv import load_dotenv
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from node.storage.db.models import Base
from node.config import LOCAL_DB_NAME, LOCAL_DB_PORT

load_dotenv()

file_path = Path(__file__).parent.resolve()
alembic_ini_path = file_path / "alembic.ini"
alembic_folder_path = file_path / "alembic"
alembic_versions_path = alembic_folder_path / "versions"

LOCAL_DB_URL = f"postgresql://{os.getenv('LOCAL_DB_USER')}:{os.getenv('LOCAL_DB_PASSWORD')}@localhost:{LOCAL_DB_PORT}/{LOCAL_DB_NAME}"

def init_db():
    # Create the SQLAlchemy engine
    engine = create_engine(LOCAL_DB_URL)

    # Create an Alembic configuration object
    alembic_cfg = Config(alembic_ini_path)
    
    # Set the SQLAlchemy URL in the Alembic configuration
    alembic_cfg.set_main_option("sqlalchemy.url", LOCAL_DB_URL)

    # Create the versions directory if it doesn't exist
    if not os.path.exists(alembic_versions_path):
        os.makedirs(alembic_versions_path)

    # Generate an initial migration
    command.revision(alembic_cfg, autogenerate=True, message="Initial migration")

    # Apply the migration to the database
    command.upgrade(alembic_cfg, "head")

    print("Database initialization complete.")

if __name__ == "__main__":
    init_db()