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
DEV_MODE=True
PROVIDER_TYPES=["models", "storage", "modules"]

# Servers
HTTP_PORT=7001
NUM_SERVERS=1
SERVER_TYPE="http" # grpc or ws
NODE_IP="pro-model-sturgeon.ngrok-free.app"
NODE_PORT=7002
ROUTING_TYPE="direct"
ROUTING_URL="ws://node.naptha.ai:8765"

# MQ
CELERY_BROKER_URL="amqp://rabbitmq:5672/"

# LLMs Inference
LITELLM_URL="http://localhost:4000" # TODO change all this
LLM_BACKEND="ollama"

VLLM_MODEL="NousResearch/Hermes-3-Llama-3.1-8B"
OLLAMA_MODELS="phi3:mini" # these will be pulled at startup

# OLLAMA_MODELS="phi3:mini,qwen2.5:1.5b"
OPENAI_MODELS="gpt-4o-mini"
MODELS = OLLAMA_MODELS if LLM_BACKEND == "ollama" else VLLM_MODEL

# Local DB
LOCAL_DB_PORT=5432
LOCAL_DB_NAME="postgres"

# Storage
file_path = Path(__file__).resolve()
repo_dir = file_path.parent.parent
BASE_OUTPUT_DIR=f"{repo_dir}/node/storage/fs"
MODULES_SOURCE_DIR=f"{repo_dir}/node/storage/hub/modules"
IPFS_GATEWAY_URL="/dns/provider.akash.pro/tcp/31832/http"

# Hub
LOCAL_HUB=False
LOCAL_HUB_URL="ws://surrealdb:8000/rpc"
PUBLIC_HUB_URL="ws://node.naptha.ai:3001/rpc"
HUB_HOSTNAME='surrealdb' # docker
HUB_DB_PORT=8000
HUB_NS="naptha"
HUB_DB="naptha"

def get_node_config():
    """Get the node configuration."""
    from node.user import get_public_key
    public_key = get_public_key(os.getenv("PRIVATE_KEY"))
    node_config = NodeConfig(
        id=f"node:{public_key}",
        owner=os.getenv("HUB_USERNAME"),
        public_key=public_key,
        ip=NODE_IP,
        server_type=SERVER_TYPE,
        http_port=HTTP_PORT,
        num_servers=NUM_SERVERS,
        provider_types=PROVIDER_TYPES,
        servers=[NodeServer(server_type=SERVER_TYPE, port=NODE_PORT+i, node_id=f"node:{public_key}") for i in range(NUM_SERVERS)],
        models=[MODELS],
        docker_jobs=DOCKER_JOBS,
        routing_type=ROUTING_TYPE,
        routing_url=ROUTING_URL,
        num_gpus=NUM_GPUS,
        arch=platform.machine(),
        os=platform.system(),
        ram=psutil.virtual_memory().total,
        vram=VRAM,
    )
    print("Created node config:", node_config)
    return node_config