import os
from dotenv import load_dotenv
import jwt
import json
import logging
import websockets
from datetime import datetime
from node.schemas import AgentRun, AgentRunInput
from node.config import DB_URL, DB_NS, DB_DB
from surrealdb import Surreal
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)
load_dotenv()

WS_PAYLOAD_THRESHOLD = 1024 * 1024  # 1MB
MAX_WS_PAYLOAD = 1024 * 1024 * 15  # 15MB


class DB:
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
            logger.info(
                f"Signing in... username: {self.username}, NS: {self.ns}, DB: {self.db}"
            )
            user = await self.surrealdb.signin(
                {
                    "user": self.username,
                    "pass": self.password,
                }
            )
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
        logger.info(f"Creating user: {user_input}")
        user = await self.surrealdb.create("user", user_input)
        if isinstance(user, list):
            return user[0]
        return user

    async def get_user(self, user_input: Dict) -> Optional[Dict]:
        user_id = "user:" + user_input["public_key"]
        logger.info(f"Getting user: {user_id}")
        return await self.surrealdb.select(user_id)

    async def _ws_create_agent_run(self, agent_run_input: AgentRunInput) -> AgentRun:
        logger.info("Creating agent run using websocket")
        try:
            async with websockets.connect(
                self.db_url, max_size=MAX_WS_PAYLOAD
            ) as websocket:
                # signin
                await websocket.send(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "signin",
                            "params": [{"user": self.username, "pass": self.password}],
                        }
                    )
                )
                response = await websocket.recv()
                # use
                await websocket.send(
                    json.dumps({"id": 2, "method": "use", "params": [self.ns, self.db]})
                )
                response = await websocket.recv()
                # create
                agent_run_params = agent_run_input.model_dict()
                if "id" in agent_run_params:
                    id_ = agent_run_params.pop("id")
                    if id_ is None:
                        id_ = "agent_run"
                else:
                    id_ = "agent_run"
                logger.info(f"Creating agent run with ID: {id_}")
                await websocket.send(
                    json.dumps(
                        {"id": 3, "method": "create", "params": [id_, agent_run_params]}
                    )
                )
                response = await websocket.recv()
                return AgentRun(**json.loads(response)["result"][0])
        except Exception as e:
            logger.error(f"Failed to create agent run: {e}")
            raise

    async def _get_agent_run(self, agent_run_id: str) -> AgentRun:
        logger.info(f"Getting agent run using websocket: {agent_run_id}")
        try:
            async with websockets.connect(
                self.db_url, max_size=MAX_WS_PAYLOAD
            ) as websocket:
                # signin
                await websocket.send(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "signin",
                            "params": [{"user": self.username, "pass": self.password}],
                        }
                    )
                )
                response = await websocket.recv()
                # use
                await websocket.send(
                    json.dumps({"id": 2, "method": "use", "params": [self.ns, self.db]})
                )
                response = await websocket.recv()
                # get
                await websocket.send(
                    json.dumps({"id": 3, "method": "select", "params": [agent_run_id]})
                )
                response = await websocket.recv()
                response = json.loads(response)
                return AgentRun(**response["result"])
        except Exception as e:
            logger.error(f"Failed to get agent run: {e}")
            raise

    async def _ws_update_agent_run(
        self, agent_run_id: str, agent_run: AgentRun
    ) -> AgentRun:
        logger.info(f"Updating agent run using websocket: {agent_run_id}")
        try:
            async with websockets.connect(
                self.db_url, max_size=MAX_WS_PAYLOAD
            ) as websocket:
                # signin
                await websocket.send(
                    json.dumps(
                        {
                            "id": 1,
                            "method": "signin",
                            "params": [{"user": self.username, "pass": self.password}],
                        }
                    )
                )
                response = await websocket.recv()

                # use
                await websocket.send(
                    json.dumps({"id": 2, "method": "use", "params": [self.ns, self.db]})
                )
                response = await websocket.recv()

                # update
                await websocket.send(
                    json.dumps(
                        {
                            "id": 3,
                            "method": "update",
                            "params": [agent_run_id, agent_run.model_dict()],
                        }
                    )
                )
                response = await websocket.recv()
                return AgentRun(**json.loads(response)["result"])
        except Exception as e:
            logger.error(f"Failed to update agent run: {e}")
            raise

    async def get_user_by_public_key(self, public_key: str) -> Optional[Dict]:
        result = await self.surrealdb.query(
            "SELECT * FROM user WHERE public_key = $public_key LIMIT 1",
            {"public_key": public_key},
        )
        if result and result[0]["result"]:
            return result[0]["result"][0]
        return None

    async def create_agent_run(self, agent_run_input: AgentRunInput) -> AgentRun:
        logger.info("Creating agent run")

        input_dict = agent_run_input.model_dict()
        input_dict = {k: v for k, v in input_dict.items() if v is not None}
        input_dict = self._convert_datetimes(input_dict)
        input_json = json.dumps(input_dict)

        if len(input_json) > WS_PAYLOAD_THRESHOLD:
            logger.info("Creating agent run using websocket")
            return await self._ws_create_agent_run(agent_run_input)
        else:
            logger.info("Creating agent run using SurrealDB")
            try:
                agent_run = await self.surrealdb.create("agent_run", input_dict)
                logger.info("Created agent run")
                if isinstance(agent_run, list):
                    agent_run = agent_run[0]
                return AgentRun(**agent_run)
            except Exception as e:
                logger.error(f"Failed to create agent run: {e}")
                raise

    async def update_agent_run(self, agent_run_id: str, agent_run: AgentRun) -> bool:
        logger.info(f"Updating agent run: {agent_run_id}")

        input_dict = agent_run.model_dict()
        input_dict = {k: v for k, v in input_dict.items() if v is not None}
        # input_dict = self._convert_datetimes(input_dict)
        input_json = json.dumps(input_dict)

        if len(input_json) > WS_PAYLOAD_THRESHOLD:
            return await self._ws_update_agent_run(agent_run_id, agent_run)
        else:
            try:
                return await self.surrealdb.update(agent_run_id, input_dict)
            except Exception as e:
                logger.error(f"Failed to update agent run: {e}")
                raise

    async def list_agent_runs(self, agent_run_id=None) -> List[AgentRun]:
        logger.info(f"Listing agent runs with ID: {agent_run_id}")
        try:
            if agent_run_id is None:
                agent_runs = await self.surrealdb.select("agent_run")
                return [AgentRun(**agent_run) for agent_run in agent_runs]
            else:
                try:
                    agent_run = await self.surrealdb.select(agent_run_id)
                    agent_run = AgentRun(**agent_run)
                except Exception as e:
                    logger.error(f"Failed to list agent runs: {e}")
                    agent_run = await self._get_agent_run(agent_run_id)

                if agent_run is None:
                    agent_run = await self._get_agent_run(agent_run_id)
                return agent_run
        except Exception as e:
            logger.error(f"Failed to list agent runs: {e}")
            raise

    async def delete_agent_run(self, agent_run_id: str) -> bool:
        try:
            await self.surrealdb.delete(agent_run_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete agent run: {e}")
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
