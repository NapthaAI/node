import os
import jwt
import logging
import subprocess
from typing import Dict, List
from surrealdb import Surreal
from dotenv import load_dotenv

load_dotenv()


def get_logger(name: str):
    """Get logger"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = get_logger(__name__)


def import_surql():
    """Import SURQL files to the database"""
    logger.info("Importing SURQL files")
    import_files = [
        "../hub/surrdb/user.surql",
        "../hub/surrdb/job.surql",
        "../hub/surrdb/auth.surql",
        "../hub/surrdb/node.surql",
    ]

    for file in import_files:
        command = f"""surreal import \
                      --conn http://localhost:{os.getenv('DB_PORT')} \
                      --user {os.getenv('DB_ROOT_USER')} \
                      --pass {os.getenv('DB_ROOT_PASS')} \
                      --ns {os.getenv('DB_NS')} \
                      --db {os.getenv('DB_DB')} \
                    {file}"""

        try:
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
    command = f"""surreal start memory -A --auth \
                  --user {os.getenv('DB_ROOT_USER')} \
                  --bind 0.0.0.0:{os.getenv('DB_PORT')} \
                  --pass {os.getenv('DB_ROOT_PASS')}"""

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

    logger.info("Database initialized")

    import_surql()


class DB:
    """Database class to handle all database operations"""

    class _db_context:
        def __init__(self, db_client, ns, db):
            self.db_client = db_client
            self.ns = ns
            self.db = db

        async def __aenter__(self):
            try:
                await self.db_client.connect()
                await self.db_client.use(namespace=self.ns, database=self.db)
                logger.info("Successfully connected to Surreal server.")
                return self.db_client
            except Exception as e:
                logger.error(f"Failed to connect to Surreal server: {e}")
                raise

        async def __aexit__(self, exc_type, exc, tb):
            await self.db_client.close()

    def __init__(self):
        self.endpoint = self._get_env_var("DB_ENDPOINT")
        self.ns = self._get_env_var("DB_NS")
        self.db = self._get_env_var("DB_DB")
        self.db_client = Surreal(self.endpoint)

        init_db()

    def _decode_token(self, token: str) -> str:
        return jwt.decode(token, options={"verify_signature": False})["ID"]

    def _get_env_var(self, var_name: str):
        value = os.environ.get(var_name)
        if not value:
            logger.error(f"{var_name} not set")
            raise Exception(f"{var_name} not set")
        return value

    async def _perform_auth(self, username: str, password: str) -> bool:
        auth_details = {
            "NS": self.ns,
            "DB": self.db,
            "SC": "user",
            "username": username,
            "password": password,
        }

        try:
            await self.db_client.signin(auth_details)
            return True
        except Exception as e:
            logger.error(f"Failed to authenticate user: {e}")
            return False

    async def signup(self, signup_details: Dict) -> (str, str):
        signup_details["NS"] = self.ns
        signup_details["DB"] = self.db
        signup_details["SC"] = "user"

        async with self._db_context(self.db_client, self.ns, self.db):
            token = await self.db_client.signup(signup_details)

        user_id = self._decode_token(token)
        return token, user_id

    async def signin(self, signin_details: Dict) -> (str, str):
        signin_details["NS"] = self.ns
        signin_details["DB"] = self.db
        signin_details["SC"] = "user"

        async with self._db_context(self.db_client, self.ns, self.db):
            token = await self.db_client.signin(signin_details)

        user_id = self._decode_token(token)
        return token, user_id

    async def get_user_id(self, token: str) -> (bool, str):
        async with self._db_context(self.db_client, self.ns, self.db):
            user = await self.db_client.authenticate(token)

        if not user:
            return False, None

        user_id = self._decode_token(token)
        return True, user_id

    async def get_user(self, user_id: str) -> Dict:
        async with self._db_context(self.db_client, self.ns, self.db):
            user = await self.db_client.select(user_id)
        return user

    async def validate_token(self, token: str) -> bool:
        async with self._db_context(self.db_client, self.ns, self.db):
            user = await self.db_client.authenticate(token)
        return True if user else False

    async def invalidate_token(self, token: str) -> bool:
        async with self._db_context(self.db_client, self.ns, self.db):
            await self.db_client.invalidate(token)
        return True

    async def create_node(
        self, node: Dict, username: str, password: str
    ) -> (bool, Dict):
        async with self._db_context(self.db_client, self.ns, self.db):
            await self._perform_auth(username, password)
            node_record = await self.db_client.create("node", node)

        if not node_record:
            return False, None
        return True, node_record

    async def get_node(self, node_id: str, username: str, password: str) -> Dict:
        async with self._db_context(self.db_client, self.ns, self.db):
            await self._perform_auth(username, password)
            node = await self.db_client.select(node_id)

        return node

    async def update_node(
        self, node_id: str, node: Dict, username: str, password: str
    ) -> bool:
        async with self._db_context(self.db_client, self.ns, self.db):
            await self._perform_auth(username, password)
            await self.db_client.update(node_id, node)

        return True

    async def list_nodes(self, username: str, password: str) -> List:
        async with self._db_context(self.db_client, self.ns, self.db):
            await self._perform_auth(username, password)
            nodes = await self.db_client.select("node")

        logger.info(f"Nodes: {nodes}")
        return nodes

    async def delete_node(self, node_id: str, username: str, password: str) -> bool:
        try:
            async with self._db_context(self.db_client, self.ns, self.db):
                await self._perform_auth(username, password)
                await self.db_client.delete(node_id)

            return True
        except Exception as e:
            logger.error(f"Failed to delete node: {e}")
            return False

    async def create_job(self, job: Dict, username: str, password: str) -> (bool, Dict):
        async with self._db_context(self.db_client, self.ns, self.db):
            await self._perform_auth(username, password)
            job_record = await self.db_client.create("job", job)

        if not job_record:
            return False, None
        return True, job_record

    async def get_job(self, job_id: str, username: str, password: str) -> Dict:
        async with self._db_context(self.db_client, self.ns, self.db):
            await self._perform_auth(username, password)
            job = await self.db_client.select(job_id)

        return job

    async def update_job(
        self, job_id: str, job: Dict, username: str, password: str
    ) -> bool:
        async with self._db_context(self.db_client, self.ns, self.db):
            await self._perform_auth(username, password)
            await self.db_client.update(job_id, job)

        return True

    async def list_jobs(self, username: str, password: str) -> List:
        async with self._db_context(self.db_client, self.ns, self.db):
            await self._perform_auth(username, password)
            jobs = await self.db_client.select("job")

        logger.info(f"Jobs: {jobs}")
        return jobs

    async def delete_job(self, job_id: str, username: str, password: str) -> bool:
        try:
            async with self._db_context(self.db_client, self.ns, self.db):
                await self._perform_auth(username, password)
                await self.db_client.delete(job_id)

            return True
        except Exception as e:
            logger.error(f"Failed to delete job: {e}")
            return False

    async def query(self, query: str, username: str, password: str) -> List:
        async with self._db_context(self.db_client, self.ns, self.db):
            await self._perform_auth(username, password)
            results = await self.db_client.query(query)

        return results
