import os
import platform
import psutil
from node.schemas import NodeConfig
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
DEV_MODE=True

# Servers
NODE_TYPE="direct"
SERVER_TYPE="http" # http or ws
NODE_IP="http://localhost"
NODE_PORT=7001
NODE_ROUTING="ws://node.naptha.ai:8765"
NUM_SERVERS=1

# MQ
CELERY_BROKER_URL="amqp://localhost:5672/"

# LLMs
LLM_BACKEND="vllm"
VLLM_MODEL="NousResearch/Hermes-3-Llama-3.1-8B"
OLLAMA_MODELS="phi"

# Local DB
LOCAL_DB_PORT=3002
LOCAL_DB_USER="naptha"
LOCAL_DB_PASSWORD="napthapassword"
LOCAL_DB_NAME="naptha"
LOCAL_DB_URL=f"postgresql://{LOCAL_DB_USER}:{LOCAL_DB_PASSWORD}@localhost:{LOCAL_DB_PORT}/{LOCAL_DB_NAME}"

# Storage
file_path = Path(__file__).resolve()
repo_dir = file_path.parent.parent
BASE_OUTPUT_DIR=f"{repo_dir}/node/storage/fs"
AGENTS_SOURCE_DIR=f"{repo_dir}/node/storage/hub/agents"
IPFS_GATEWAY_URL="/dns/provider.akash.pro/tcp/31832/http"

# Hub
LOCAL_HUB=False
LOCAL_HUB_URL="ws://localhost:3001/rpc"
PUBLIC_HUB_URL="ws://node.naptha.ai:3001/rpc"
HUB_DB_PORT=3001
HUB_NS="naptha"
HUB_DB="naptha"

def get_node_config():
    """Get the node configuration."""
    from node.user import get_public_key
    public_key = get_public_key(os.getenv("PRIVATE_KEY"))
    return NodeConfig(
        id=f"node:{public_key}",
        public_key=public_key,
        ip=NODE_IP,
        ports=[NODE_PORT+i for i in range(NUM_SERVERS)],
        routing=NODE_ROUTING,
        ollama_models=[OLLAMA_MODELS],
        num_gpus=NUM_GPUS,
        vram=VRAM,
        os=platform.system(),
        arch=platform.machine(),
        ram=psutil.virtual_memory().total,
        docker_jobs=DOCKER_JOBS,
        owner=os.getenv("HUB_USERNAME"),
        num_servers=NUM_SERVERS,
        node_type=NODE_TYPE,
        server_type=SERVER_TYPE,
    )