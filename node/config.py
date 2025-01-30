import os
import platform
import psutil
from node.schemas import NodeConfig, NodeServer
from pathlib import Path
from dotenv import load_dotenv

FILE_PATH = Path(__file__).resolve()
NODE_PATH = FILE_PATH.parent
load_dotenv()

# Node
IN_DOCKER=False
GPU=False # set to true if gpu is available (Only for running node with IN_DOCKER=true)
NUM_GPUS=0
VRAM=0
DOCKER_JOBS=False
PROVIDER_TYPES=["models", "storage", "modules"]

# Servers
USER_COMMUNICATION_PORT=7001
USER_COMMUNICATION_PROTOCOL="http" # http or https
NUM_NODE_COMMUNICATION_SERVERS=1
NODE_COMMUNICATION_PORT=7002
NODE_COMMUNICATION_PROTOCOL="ws" # grpc or ws
NODE_IP="pro-model-sturgeon.ngrok-free.app"
ROUTING_TYPE="direct"
ROUTING_URL="ws://node.naptha.ai:8765"

# LLMs Inference
LITELLM_URL="http://litellm:4000" # TODO change all this
LLM_BACKEND="ollama"

VLLM_MODEL="NousResearch/Hermes-3-Llama-3.1-8B"
OLLAMA_MODELS="NousResearch/Hermes-3-Llama-3.1-8B" # these will be pulled at startup

# OLLAMA_MODELS="phi3:mini,qwen2.5:1.5b"
OPENAI_MODELS="gpt-4o-mini"
MODELS = OLLAMA_MODELS if LLM_BACKEND == "ollama" else VLLM_MODEL

# Local DB
LOCAL_DB_POSTGRES_PORT=3002
LOCAL_DB_POSTGRES_NAME="naptha"

# Storage
file_path = Path(__file__).resolve()
repo_dir = file_path.parent.parent
BASE_OUTPUT_DIR=f"{repo_dir}/node/storage/fs"
MODULES_SOURCE_DIR=f"{repo_dir}/node/storage/hub/modules"
# IPFS_GATEWAY_URL="/dns/provider.akash.pro/tcp/31832/http"
IPFS_GATEWAY_URL="http://ipfs.naptha.work:30798"

# Hub
LOCAL_HUB=False
REGISTER_NODE_WITH_HUB=False # set to true if you want your node to be available as a provider
LOCAL_HUB_URL="ws://localhost:3001/rpc"
PUBLIC_HUB_URL="ws://node.naptha.ai:3001/rpc"
HUB_DB_SURREAL_PORT=3001
HUB_DB_SURREAL_NS="naptha"
HUB_DB_SURREAL_NAME="naptha"

def get_node_config():
    """Get the node configuration."""
    from node.user import get_public_key
    public_key = get_public_key(os.getenv("PRIVATE_KEY"))
    node_config = NodeConfig(
        id=f"node:{public_key}",
        owner=os.getenv("HUB_USERNAME"),
        public_key=public_key,
        ip=NODE_IP,
        user_communication_protocol=USER_COMMUNICATION_PROTOCOL,
        user_communication_port=USER_COMMUNICATION_PORT,
        node_communication_protocol=NODE_COMMUNICATION_PROTOCOL,
        num_node_communication_servers=NUM_NODE_COMMUNICATION_SERVERS,
        provider_types=PROVIDER_TYPES,
        servers=[NodeServer(communication_protocol=NODE_COMMUNICATION_PROTOCOL, port=NODE_COMMUNICATION_PORT+i, node_id=f"node:{public_key}") for i in range(NUM_NODE_COMMUNICATION_SERVERS)],
        models=[MODELS],
        docker_jobs=DOCKER_JOBS,
        routing_type=ROUTING_TYPE,
        routing_url=ROUTING_URL,
        ports=[NODE_COMMUNICATION_PORT+i for i in range(NUM_NODE_COMMUNICATION_SERVERS)],
        num_gpus=NUM_GPUS,
        arch=platform.machine(),
        os=platform.system(),
        ram=psutil.virtual_memory().total,
        vram=VRAM,
    )
    print("Created node config:", node_config)
    return node_config
