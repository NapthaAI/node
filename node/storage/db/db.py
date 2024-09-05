
from dotenv import load_dotenv
import jwt
from naptha_sdk.schemas import ModuleRun, ModuleRunInput
from node.utils import get_logger, AsyncMixin
import os
from surrealdb import Surreal
from typing import Dict, List, Tuple, Optional

logger = get_logger(__name__)
load_dotenv()


class DB(AsyncMixin):
    """Database class to handle all database operations"""

    def __init__(self):
        self.db_url = os.getenv("DB_URL")
        self.ns = os.getenv("DB_NS")
        self.db = os.getenv("DB_DB")
        self.username = os.getenv("DB_ROOT_USER")
        self.password = os.getenv("DB_ROOT_PASS")

        self.surrealdb = Surreal(self.db_url)
        self.is_authenticated = False
        self.initialized = True
        super().__init__()

    async def __ainit__(self, *args, **kwargs):
        """Async constructor"""
        self.hub = await self._authenticated_db()

    async def _authenticated_db(self):
        try:
            await self.surrealdb.connect()
            await self.surrealdb.use(namespace=self.ns, database=self.db)
            success, token, user_id = await self.signin()
            self.is_authenticated = True
            return success, token, user_id
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise

    async def signin(self) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            logger.info(f"Signing in... username: {self.username}, NS: {self.ns}, DB: {self.db}")
            user = await self.surrealdb.signin({
                "NS": self.ns,
                "DB": self.db,
                "user": self.username,
                "pass": self.password,
            })
            user_id = self._decode_token(user)
            return True, user, user_id
        except Exception as e:
            logger.error(f"Sign in failed: {e}")
            return False, None, None

    def _decode_token(self, token: str) -> str:
        try:
            return jwt.decode(token, options={"verify_signature": False})["ID"]
        except jwt.PyJWTError as e:
            logger.error(f"Token decoding failed: {e}")
            return None

    async def get_user_id(self, token: str) -> Tuple[bool, Optional[str]]:
        user_id = self._decode_token(token)
        return (True, user_id) if user_id else (False, None)

    async def create_user(self, user_input: Dict) -> Tuple[bool, Optional[Dict]]:
        user = await self.surrealdb.create("user", user_input)
        return user[0]

    async def get_user(self, user_input: Dict) -> Optional[Dict]:
        user_id = "user:" + user_input['public_key']
        logger.info(f"Getting user: {user_id}")
        return await self.surrealdb.select(user_id)

    async def create_module_run(self, module_run_input: ModuleRunInput) -> ModuleRun:
        logger.info(f"Creating module run: {module_run_input.model_dict()}")
        module_run = await self.surrealdb.create("module_run", module_run_input.model_dict())
        logger.info(f"Created module run: {module_run_input}")
        module_run = module_run[0]
        return ModuleRun(**module_run)

    async def update_module_run(self, module_run_id: str, module_run: ModuleRun) -> bool:
        logger.info(f"Updating module run {module_run_id}: {module_run.model_dict()}")
        return await self.surrealdb.update(module_run_id, module_run.model_dict())

    async def list_module_runs(self, module_run_id=None) -> List[ModuleRun]:
        logger.info(f'Listing module runs with ID: {module_run_id}')
        if module_run_id is None:
            module_runs = await self.surrealdb.select("module_run")
            return [ModuleRun(**module_run) for module_run in module_runs]
        else:
            module_run = await self.surrealdb.select(module_run_id)
            logger.info(f'Found module run with ID {module_run_id}: {module_run}')
            return ModuleRun(**module_run)

    async def delete_module_run(self, module_run_id: str) -> bool:
        try:
            await self.surrealdb.delete(module_run_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete module run: {e}")
            return False

    async def query(self, query: str) -> List:
        return await self.surrealdb.query(query)

    async def close(self):
        if self.is_authenticated:
            await self.surrealdb.close()
            self.is_authenticated = False
            logger.info("Database connection closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

