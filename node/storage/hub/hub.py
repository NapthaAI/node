from dotenv import load_dotenv
import jwt
import logging
from node.utils import AsyncMixin
from node.config import HUB_DB_SURREAL_NAME, HUB_DB_SURREAL_NS, LOCAL_HUB_URL, LOCAL_HUB, PUBLIC_HUB_URL
from node.schemas import Module, NodeConfig, NodeServer
import os
from surrealdb import Surreal
import traceback
from typing import Dict, List, Optional, Tuple

load_dotenv()
logger = logging.getLogger(__name__)


class HubDBSurreal(AsyncMixin):
    def __init__(self, *args, **kwargs):
        if LOCAL_HUB:
            self.hub_url = LOCAL_HUB_URL
        else:
            self.hub_url = PUBLIC_HUB_URL
        self.ns = HUB_DB_SURREAL_NS
        self.db = HUB_DB_SURREAL_NAME

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

    async def get_server(self, server_name: str=None, server_id: str=None) -> Optional[Dict]:
        if server_name:
            result = await self.surrealdb.query("SELECT * FROM server WHERE name = $server_name LIMIT 1", {"name": server_name})
        elif server_id:
            result = await self.surrealdb.select(server_id)
        return result

    async def create_server(self, server_config: NodeServer):
        """Create a server record in the database"""
        logger.info(f"Creating server: {server_config}")
        server = await self.surrealdb.create("server", server_config)
        logger.info(f"created server: {server}")
        if isinstance(server, dict):
            return server
        return server[0]
    
    async def create_node(self, node_config: NodeConfig, servers: Optional[List[str]]=None) -> Dict:
        node_config.owner = self.user_id
        node_id = node_config.id

        # Create server records first
        server_records = []
        if servers:
            for server in servers:
                s = await self.create_server(server)
                server_records.append(s['id'])
            # Add server records to node_config
            node_config.servers = server_records

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

    async def list_nodes(self, node_ip=None) -> List:
        logging.info('listing nodes...')
        if not node_ip:
            logging.info('Node IP not specified, listing...')
            nodes = await self.surrealdb.query("SELECT * FROM node;")
            logging.info(f'Got nodes: {nodes}')
            return nodes[0]['result']
        else:
            logging.info('Getting node...')
            nodes = await self.surrealdb.query("SELECT * FROM node WHERE ip=$node_ip;", {"node_ip": node_ip})
            if not nodes or not nodes[0].get("result"):
                raise Exception(f"Node {node_ip} not found in hub. Please check if the node is registered.")
            node = nodes[0]['result'][0]
            server_ids = node['servers']
            servers = []
            for server_id in server_ids:
                server = await self.surrealdb.select(server_id)
                servers.append(server)
            node['servers'] = [NodeServer(**server) for server in servers]

            alt_ports = [
                server['port'] 
                for server in servers
                if server['communication_protocol'] in ['ws', 'grpc']
            ]
            node['ports'] = alt_ports
            return NodeConfig(**node)

    async def delete_node(self, node_id: str, servers: Optional[List[str]]=None) -> bool:
        # Delete server records first
        if servers:
            for server in servers:
                try:
                    await self.delete_server(server)
                except Exception as e:
                    logger.error(f"Error deleting server: {e}")
                    return False
        return await self.surrealdb.delete(node_id)
    
    async def delete_server(self, server_id: str) -> bool:
        return await self.surrealdb.delete(server_id)

    async def list_modules(self, module_type: str, module_name: str = None) -> List:
        """
        List modules from the database.
        
        Args:
            module_type: Type of module (agent, tool, orchestrator, environment, kb, memory, persona)
            module_name: Optional name to filter by
        """
        try:
            if ':' in str(module_name):
                module_name = module_name.split(':')[1]

            if not module_name:
                result = await self.surrealdb.query(f"SELECT * FROM {module_type};")
                if not result or not result[0].get("result"):
                    return []
                return [Module(**item) for item in result[0]["result"]]
            else:
                result = await self.surrealdb.query(
                    f"SELECT * FROM {module_type} WHERE name = $module_name LIMIT 1;",
                    {"module_name": module_name}
                )
                if not result or not result[0].get("result") or not result[0]["result"]:
                    return None
                return Module(**result[0]["result"][0])
        except Exception as e:
            logger.error(f"Error querying {module_type} from database: {e}")
            raise e
        
    async def list_agents(self, agent_name=None) -> List:
        return await self.list_modules("agent", agent_name)
    
    async def list_tools(self, tool_name=None) -> List:
        return await self.list_modules("tool", tool_name)
    
    async def list_orchestrators(self, orchestrator_name=None) -> List:
        return await self.list_modules("orchestrator", orchestrator_name)
    
    async def list_environments(self, environment_name=None) -> List:
        return await self.list_modules("environment", environment_name)
    
    async def list_personas(self, persona_name=None) -> List:
        return await self.list_modules("persona", persona_name)

    async def list_knowledge_bases(self, knowledge_base_name=None) -> List:
        return await self.list_modules("kb", knowledge_base_name)
    
    async def list_memory_modules(self, memory_module_name=None) -> List:
        return await self.list_modules("memory", memory_module_name)

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

async def list_modules(module_type: str, module_name: str) -> List:

    if module_type == "agent":
        list_func = lambda hub: hub.list_agents(module_name)
    elif module_type == "tool":
        list_func = lambda hub: hub.list_tools(module_name)
    elif module_type == "orchestrator":
        list_func = lambda hub: hub.list_orchestrators(module_name)
    elif module_type == "environment":
        list_func = lambda hub: hub.list_environments(module_name)
    elif module_type == "kb":
        list_func = lambda hub: hub.list_knowledge_bases(module_name)
    elif module_type == "memory":
        list_func = lambda hub: hub.list_memory_modules(module_name)
    elif module_type == "persona":
        list_func = lambda hub: hub.list_personas(module_name)

    hub_username = os.getenv("HUB_USERNAME")
    hub_password = os.getenv("HUB_PASSWORD")
    if not hub_username or not hub_password:
        raise ValueError("Missing Hub authentication credentials - HUB_USERNAME and HUB_PASSWORD environment variables must be set")

    if module_type not in ["agent", "tool", "orchestrator", "environment", "kb", "memory", "persona"]:
        raise ValueError(f"Invalid module type: {module_type}. Must be one of: agent, tool, orchestrator, environment, kb, memory")

    if not module_name:
        raise ValueError("Module name cannot be empty")

    async with HubDBSurreal() as hub:
        try:
            _, _, _ = await hub.signin(hub_username, hub_password)
        except Exception as auth_error:
            raise ConnectionError(f"Failed to authenticate with Hub: {str(auth_error)}")

        try:
            module = await list_func(hub)
        except Exception as list_error:
            raise RuntimeError(f"Failed to list {module_type} module: {str(list_error)}")

        if not module:
            raise ValueError(f"{module_type.capitalize()} module '{module_name}' not found")

        return module
    
async def list_nodes(node_ip: str) -> List:

    hub_username = os.getenv("HUB_USERNAME")
    hub_password = os.getenv("HUB_PASSWORD")

    async with HubDBSurreal() as hub:
        try:
            _, _, _ = await hub.signin(hub_username, hub_password)
        except Exception as auth_error:
            raise ConnectionError(f"Failed to authenticate with Hub: {str(auth_error)}")

        node = await hub.list_nodes(node_ip=node_ip)
        return node

