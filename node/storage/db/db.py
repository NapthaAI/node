import os
import jwt
from surrealdb import Surreal
from dotenv import load_dotenv
from node.utils import get_logger
from typing import Dict, List, Tuple, Optional

logger = get_logger(__name__)

load_dotenv()


class DB:
    """Database class to handle all database operations"""

    def __init__(self, *args, **kwargs):
        self.endpoint = os.getenv("DB_ENDPOINT")
        self.ns = os.getenv("DB_NS")
        self.db = os.getenv("DB_DB")
        self.username = os.getenv("DB_ROOT_USER")
        self.password = os.getenv("DB_ROOT_PASS")
        self.surrealdb = Surreal(self.endpoint)

        self.__storedargs = args, kwargs
        self.async_initialized = False

    async def __ainit__(self, *args, **kwargs):
        """Async constructor, you should implement this"""
        success, token, user_id = await self._authenticated_db()
        self.user_id, self.token = user_id, token

    async def __initobj(self):
        """Crutch used for __await__ after spawning"""
        assert not self.async_initialized
        self.async_initialized = True
        # pass the parameters to __ainit__ that passed to __init__
        await self.__ainit__(*self.__storedargs[0], **self.__storedargs[1])
        return self

    def __await__(self):
        return self.__initobj().__await__()

    async def signin(self) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            logger.info(
                f"Signing in... username: {self.username}, NS: {self.ns}, DB: {self.db}"
            )
            user = await self.surrealdb.signin(
                {
                    "NS": self.ns,
                    "DB": self.db,
                    # "SC": "user",
                    "user": self.username,
                    "pass": self.password,
                }
            )
        except Exception as e:
            logger.error(f"Sign in failed: {e}")
            return False, None, None
        user_id = self._decode_token(user)
        return True, user, user_id

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

    def _decode_token(self, token: str) -> str:
        try:
            return jwt.decode(token, options={"verify_signature": False})["ID"]
        except jwt.PyJWTError as e:
            logger.error(f"Token decoding failed: {e}")
            return None

    async def get_user_id(self, token: str) -> Tuple[bool, Optional[str]]:
        user_id = self._decode_token(token)
        if not user_id:
            return False, None
        return True, user_id

    async def create_user(self, user_input: Dict) -> Tuple[bool, Optional[Dict]]:
        user = await self.surrealdb.create("user", user_input)
        return user[0]

    async def get_user(self, user_input: Dict) -> Optional[Dict]:
        user_id = "user:" + user_input['public_key']
        logger.info(f"Getting user: {user_id}")
        return await self.surrealdb.select(user_id)

    async def create_job(self, job: Dict) -> Tuple[bool, Optional[Dict]]:
        logger.info(f"Creating job: {job}")
        return await self.surrealdb.create("consume", job)

    async def update_job(self, job_id: str, job: Dict) -> bool:
        logger.info(f"Updating job {job_id}: {job}")
        return await self.surrealdb.update(job_id, job)

    async def list_tasks(self, task_id=None) -> List:
        if task_id is None:
            return await self.surrealdb.select("consume")
        else:
            return await self.surrealdb.select(task_id)

    async def delete_job(self, job_id: str) -> bool:
        try:
            await self._perform_db_operation(self.surrealdb.delete, job_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete job: {e}")
            return False

    async def query(self, query: str) -> List:
        result = await self._perform_db_operation(self.surrealdb.query, query)
        return result


async def update_db_with_status_sync(job_data: Dict) -> None:
    """
    Update the hub with the job status synchronously
    param job_data: Job data to update
    """
    logger.info(f"Updating hub with job status: {job_data}")

    db = await DB("buyer1", "buyer1pass")

    try:
        updated_job = await db.update_job(job_data["id"], job_data)
        logger.info(f"Updated job: {updated_job}")
    except Exception as e:
        logger.error(f"Failed to update hub with job status: {e}")
        raise e
