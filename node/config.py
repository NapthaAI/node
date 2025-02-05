from pathlib import Path
import os

# Node
# True if you want to launch node in docker containers, False if you want to run in systemd services
LAUNCH_DOCKER = True
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
NODE_IP="localhost"
ROUTING_TYPE="direct"
ROUTING_URL="wss://node.naptha.ai"

# LLMs Inference: ollama or vllm
LLM_BACKEND="ollama"
OLLAMA_MODELS="hermes3:8b" # use string of models separated by commas
VLLM_MODELS=[
    "NousResearch/Hermes-3-Llama-3.1-8B",
    # "Qwen/Qwen2.5-7B-Instruct",
    # "meta-llama/Llama-3.1-8B-Instruct",
    # "Team-ACE/ToolACE-8B",
    # "ibm-granite/granite-3.1-8b-instruct",
    # "internlm/internlm2_5-7b-chat",
    # "meetkai/functionary-small-v3.1",
    # "jinaai/jina-embeddings-v2-base-en"
]
OPENAI_MODELS="gpt-4o-mini"
LITELLM_URL = "http://litellm:4000" if LAUNCH_DOCKER else "http://localhost:4000"
MODELS = OLLAMA_MODELS if LLM_BACKEND == "ollama" else VLLM_MODELS

# Local DB
LOCAL_DB_POSTGRES_PORT=5432
LOCAL_DB_POSTGRES_NAME="naptha"
LOCAL_DB_POSTGRES_HOST = "pgvector" if LAUNCH_DOCKER else "localhost"

# RMQ
RMQ_HOST = "rabbitmq" if LAUNCH_DOCKER else "localhost"

# Storage
file_path = Path(__file__).resolve()
repo_dir = file_path.parent.parent
BASE_OUTPUT_DIR=f"{repo_dir}/node/storage/fs"
MODULES_SOURCE_DIR=f"{repo_dir}/node/storage/hub/modules"
# IPFS_GATEWAY_URL="/dns/provider.akash.pro/tcp/31832/http"
IPFS_GATEWAY_URL="http://ipfs.naptha.work:30798"

# Hub
LOCAL_HUB=True
REGISTER_NODE_WITH_HUB=False # set to true if you want your node to be available as a provider
LOCAL_HUB_URL="ws://surrealdb:8000/rpc" if LAUNCH_DOCKER else "ws://localhost:3001/rpc"
PUBLIC_HUB_URL="wss://hub.naptha.ai/rpc"
HUB_DB_SURREAL_PORT=3001
HUB_DB_SURREAL_NS="naptha"
HUB_DB_SURREAL_NAME="naptha"
