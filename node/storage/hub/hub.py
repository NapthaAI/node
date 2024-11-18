from dotenv import load_dotenv
import jwt
import logging
from node.utils import AsyncMixin
from node.config import HUB_DB, HUB_NS, LOCAL_HUB_URL, LOCAL_HUB, PUBLIC_HUB_URL
from node.schemas import AgentModule, NodeConfig
from surrealdb import Surreal
import traceback
from typing import Dict, List, Optional, Tuple

load_dotenv()
logger = logging.getLogger(__name__)


class Hub(AsyncMixin):
    def __init__(self, *args, **kwargs):
        if LOCAL_HUB:
            self.hub_url = LOCAL_HUB_URL
        else:
            self.hub_url = PUBLIC_HUB_URL
        self.ns = HUB_NS
        self.db = HUB_DB

        self.surrealdb = Surreal(self.hub_url)
        self.is_authenticated = False
        self.user_id = None
        self.token = None
        super().__init__()

    async def __ainit__(self, *args, **kwargs):
        await self.connect()

    async def connect(self):
        """Connect to the database and authenticate"""
        if not self.is_authenticated:
            try:
                await self.surrealdb.connect()
                await self.surrealdb.use(namespace=self.ns, database=self.db)
            except Exception as e:
                logger.error(f"Connection failed: {e}")
                raise

    def _decode_token(self, token: str) -> str:
        try:
            return jwt.decode(token, options={"verify_signature": False})["ID"]
        except jwt.PyJWTError as e:
            logger.error(f"Token decoding failed: {e}")
            return None

    async def signin(
        self, username: str, password: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        try:
            user = await self.surrealdb.signin(
                {
                    "NS": self.ns,
                    "DB": self.db,
                    "AC": "user",
                    "username": username,
                    "password": password,
                },
            )
            self.user_id = self._decode_token(user)
            self.token = user
            self.is_authenticated = True
            return True, user, self.user_id
        except Exception as e:
            logger.error(f"Sign in failed: {e}")
            logger.error(traceback.format_exc())
            return False, None, None

    async def signup(
        self, username: str, password: str, public_key: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        user = await self.surrealdb.signup(
            {
                "NS": self.ns,
                "DB": self.db,
                "AC": "user",
                "name": username,
                "username": username,
                "password": password,
                "public_key": public_key,
            }
        )
        if not user:
            return False, None, None
        self.user_id = self._decode_token(user)
        return True, user, self.user_id

    async def get_user(self, user_id: str) -> Optional[Dict]:
        return await self.surrealdb.select(user_id)

    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        result = await self.surrealdb.query(
            "SELECT * FROM user WHERE username = $username LIMIT 1",
            {"username": username},
        )
        if result and result[0]["result"]:
            return result[0]["result"][0]
        return None

    async def get_user_by_public_key(self, public_key: str) -> Optional[Dict]:
        result = await self.surrealdb.query(
            "SELECT * FROM user WHERE public_key = $public_key LIMIT 1",
            {"public_key": public_key},
        )
        if result and result[0]["result"]:
            return result[0]["result"][0]
        return None

    async def create_node(self, node_config: NodeConfig) -> Dict:
        node_config.owner = self.user_id
        node_id = node_config.id
        logger.info(f"Creating node: {node_config}")
        self.node_config = await self.surrealdb.create(node_id, node_config)
        logger.info(f"Created node: {self.node_config}")
        if self.node_config is None:
            raise Exception("Failed to register node")
        if isinstance(self.node_config, dict):
            return self.node_config
        return self.node_config[0]

    async def get_node(self, node_id: str) -> Optional[Dict]:
        return await self.surrealdb.select(node_id)

    async def update_node(self, node_id: str, node: Dict) -> bool:
        return await self.surrealdb.update(node_id, node)

    async def list_nodes(self) -> List:
        return await self.surrealdb.select("node")

    async def delete_node(self, node_id: str) -> bool:
        return await self.surrealdb.delete(node_id)

    async def list_agents(self, agent_name=None) -> List:
        if not agent_name:
            agents = await self.surrealdb.query("SELECT * FROM agent;")
            return [AgentModule(**agent) for agent in agents[0]["result"]]
        else:
            agent = await self.surrealdb.query(
                "SELECT * FROM agent WHERE id=$agent_name;", {"agent_name": agent_name}
            )
            try:
                return AgentModule(**agent[0]["result"][0])
            except Exception as e:
                logger.error(f"Failed to get agent: {e}")
                return None

    async def list_orchestrators(self, orchestrator_name=None) -> List:
        if not orchestrator_name:
            orchestrators = await self.surrealdb.query("SELECT * FROM orchestrator;")
            return [AgentModule(**orchestrator) for orchestrator in orchestrators[0]["result"]]
        else:
            orchestrator = await self.surrealdb.query(
                "SELECT * FROM orchestrator WHERE id=$orchestrator_name;", 
                {"orchestrator_name": orchestrator_name}
            )
            try:
                return AgentModule(**orchestrator[0]["result"][0])
            except Exception as e:
                logger.error(f"Failed to get orchestrator: {e}")
                return None

    async def create_agent(self, agent_config: Dict) -> Tuple[bool, Optional[Dict]]:
        return await self.surrealdb.create("agent", agent_config)

    async def close(self):
        """Close the database connection"""
        if self.is_authenticated:
            try:
                await self.surrealdb.close()
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
            finally:
                self.is_authenticated = False
                self.user_id = None
                self.token = None
                logger.info("Database connection closed")

    async def __aenter__(self):
        """Async enter method for context manager"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async exit method for context manager"""
        await self.close()
