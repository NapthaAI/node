
from dotenv import load_dotenv
import jwt
import json
import websockets
from datetime import datetime
from naptha_sdk.schemas import ModuleRun, ModuleRunInput
from node.config import DB_URL, DB_NS, DB_DB
from node.utils import get_logger
import os
from surrealdb import Surreal
from typing import Dict, List, Tuple, Optional

logger = get_logger(__name__)
load_dotenv()

WS_PAYLOAD_THRESHOLD = 1024*1024 # 1MB
MAX_WS_PAYLOAD = 1024*1024*15 # 15MB

class DB():
    """Database class to handle all database operations"""

    def __init__(self):
        self.db_url = DB_URL
        self.ns = DB_NS
        self.db = DB_DB
        self.username = os.getenv("DB_ROOT_USER")
        self.password = os.getenv("DB_ROOT_PASS")

        self.surrealdb = Surreal(self.db_url)
        self.is_authenticated = False
        self.initialized = True

    async def connect(self):
        """Connect to the database and authenticate"""
        if not self.is_authenticated:
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

    async def _ws_create_module_run(self, module_run_input: ModuleRunInput) -> ModuleRun:
        logger.info(f"Creating module run using websocket")
        try:
            async with websockets.connect(self.db_url, max_size=MAX_WS_PAYLOAD) as websocket:
                # signin
                await websocket.send(json.dumps({
                    "id": 1,
                    "method": "signin",
                    "params": [{"user": self.username, "pass": self.password}]
                }))
                response = await websocket.recv()
                # use
                await websocket.send(json.dumps({
                    "id": 2,
                    "method": "use",
                    "params": [self.ns, self.db]
                }))
                response = await websocket.recv()
                # create
                module_params = module_run_input.model_dict()
                if 'id' in module_params:
                    id_ = module_params.pop('id')
                    if id_ is None:
                        id_ = 'module_run'
                else:
                    id_ = 'module_run'
                logger.info(f"Creating module run with ID: {id_}")
                await websocket.send(json.dumps({
                    "id": 3,
                    "method": "create",
                    "params": [id_, module_params]
                }))
                response = await websocket.recv()
                return ModuleRun(**json.loads(response)['result'][0])
        except Exception as e:
            logger.error(f"Failed to create module run: {e}")
            raise

    async def _get_module_run(self, module_run_id: str) -> ModuleRun:
        logger.info(f"Getting module run using websocket: {module_run_id}")
        try:
            async with websockets.connect(self.db_url, max_size=MAX_WS_PAYLOAD) as websocket:
                # signin
                await websocket.send(json.dumps({
                    "id": 1,
                    "method": "signin",
                    "params": [{"user": self.username, "pass": self.password}]
                }))
                response = await websocket.recv()
                # use
                await websocket.send(json.dumps({
                    "id": 2,
                    "method": "use",
                    "params": [self.ns, self.db]
                }))
                response = await websocket.recv()
                # get
                await websocket.send(json.dumps({
                    "id": 3,
                    "method": "select",
                    "params": [module_run_id]
                }))
                response = await websocket.recv()
                response = json.loads(response)
                return ModuleRun(**response['result'])
        except Exception as e:
            logger.error(f"Failed to get module run: {e}")
            raise

    async def _ws_update_module_run(self, module_run_id: str, module_run: ModuleRun) -> ModuleRun:
        logger.info(f"Updating module run using websocket: {module_run_id}")
        try:
            async with websockets.connect(self.db_url, max_size=MAX_WS_PAYLOAD) as websocket:
                # signin
                await websocket.send(json.dumps({
                    "id": 1,
                    "method": "signin",
                    "params": [{"user": self.username, "pass": self.password}]
                }))
                response = await websocket.recv()

                # use
                await websocket.send(json.dumps({
                    "id": 2,
                    "method": "use",
                    "params": [self.ns, self.db]
                }))
                response = await websocket.recv()

                # update
                await websocket.send(json.dumps({
                    "id": 3,
                    "method": "update",
                    "params": [module_run_id, module_run.model_dict()]
                }))
                response = await websocket.recv()
                return ModuleRun(**json.loads(response)['result'])
        except Exception as e:
            logger.error(f"Failed to update module run: {e}")
            raise

    async def get_user_by_public_key(self, public_key: str) -> Optional[Dict]:
        result = await self.surrealdb.query(
            "SELECT * FROM user WHERE public_key = $public_key LIMIT 1",
            {"public_key": public_key}
        )
        if result and result[0]["result"]:
            return result[0]["result"][0]
        return None

    async def create_module_run(self, module_run_input: ModuleRunInput) -> ModuleRun:
        logger.info(f"Creating module run")

        input_dict = module_run_input.model_dict()
        input_dict = {k: v for k, v in input_dict.items() if v is not None}
        input_dict = self._convert_datetimes(input_dict)
        input_json = json.dumps(input_dict)
        
        if len(input_json) > WS_PAYLOAD_THRESHOLD:
            logger.info(f"Creating module run using websocket")
            return await self._ws_create_module_run(module_run_input)
        else:
            logger.info(f"Creating module run using SurrealDB")
            try:
                module_run = await self.surrealdb.create("module_run", input_dict)
                logger.info(f"Created module run")
                module_run = module_run[0]
                return ModuleRun(**module_run)
            except Exception as e:
                logger.error(f"Failed to create module run: {e}")
                raise 

    async def update_module_run(self, module_run_id: str, module_run: ModuleRun) -> bool:
        logger.info(f"Updating module run: {module_run_id}")

        input_dict = module_run.model_dict()
        input_dict = {k: v for k, v in input_dict.items() if v is not None}
        input_dict = self._convert_datetimes(input_dict)
        input_json = json.dumps(input_dict)

        if len(input_json) > WS_PAYLOAD_THRESHOLD:
            return await self._ws_update_module_run(module_run_id, module_run)
        else:
            try:        
                return await self.surrealdb.update(module_run_id, input_dict)
            except Exception as e:
                logger.error(f"Failed to update module run: {e}")
                raise

    async def list_module_runs(self, module_run_id=None) -> List[ModuleRun]:
        logger.info(f'Listing module runs with ID: {module_run_id}')
        try:
            if module_run_id is None:
                module_runs = await self.surrealdb.select("module_run")
                return [ModuleRun(**module_run) for module_run in module_runs]
            else:
                try:
                    module_run = await self.surrealdb.select(module_run_id)
                    module_run = ModuleRun(**module_run)
                except Exception as e:
                    logger.error(f"Failed to list module runs: {e}")
                    module_run = await self._get_module_run(module_run_id)

                if module_run is None:
                    module_run = await self._get_module_run(module_run_id)
                return module_run
        except Exception as e:
            logger.error(f"Failed to list module runs: {e}")
            raise

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
        """Close the database connection"""
        if self.is_authenticated:
            try:
                await self.surrealdb.close()
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
            finally:
                self.is_authenticated = False
                logger.info("Database connection closed")

    async def __aenter__(self):
        """Async enter method for context manager"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit method for context manager"""
        await self.close()

    def _convert_datetimes(self, obj):
        if isinstance(obj, dict):
            return {k: self._convert_datetimes(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_datetimes(v) for v in obj]
        elif isinstance(obj, datetime):
            return obj.isoformat()
        else:
            return obj