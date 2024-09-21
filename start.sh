#!/bin/bash

# Set default values for environment variables
export RMQ_USER=${RMQ_USER:-username}
export RMQ_PASSWORD=${RMQ_PASSWORD:-password}
export LLM_BACKEND=${LLM_BACKEND:-vllm}
export OLLAMA_MODELS=${OLLAMA_MODELS:-phi}
export VLLM_MODEL=${VLLM_MODEL:-"NousResearch/Hermes-3-Llama-3.1-8B"}
export NODE_TYPE=${NODE_TYPE:-direct}
export NODE_IP=${NODE_IP:-http://localhost}
export NODE_PORT=${NODE_PORT:-7001}
export NODE_ROUTING=${NODE_ROUTING:-ws://node.naptha.ai:8765}
export BASE_OUTPUT_DIR=${BASE_OUTPUT_DIR:-./storage/fs}
export AGENTS_SOURCE_DIR=${AGENTS_SOURCE_DIR:-./storage/hub/agents}
export IPFS_GATEWAY_URL=${IPFS_GATEWAY_URL:-/dns/provider.akash.pro/tcp/31832/http}
export DOCKER_JOBS=${DOCKER_JOBS:-false}
export CELERY_BROKER_URL=${CELERY_BROKER_URL:-amqp://localhost:5672/}
export LOCAL_HUB=${LOCAL_HUB:-false}
export LOCAL_HUB_URL=${LOCAL_HUB_URL:-ws://localhost:3001/rpc}
export PUBLIC_HUB_URL=${PUBLIC_HUB_URL:-ws://node.naptha.ai:3001/rpc}
export HUB_NS=${HUB_NS:-naptha}
export HUB_DB=${HUB_DB:-naptha}
export HUB_DB_PORT=${HUB_DB_PORT:-3001}
export HUB_ROOT_USER=${HUB_ROOT_USER:-root}
export HUB_ROOT_PASS=${HUB_ROOT_PASS:-root}
export HUB_USERNAME=${HUB_USERNAME:-seller1}
export HUB_PASSWORD=${HUB_PASSWORD:-great-password}
export SURREALDB_PORT=${SURREALDB_PORT:-3002}
export DB_NS=${DB_NS:-naptha}
export DB_DB=${DB_DB:-naptha}
export DB_URL=${DB_URL:-ws://localhost:3002/rpc}
export DB_ROOT_USER=${DB_ROOT_USER:-root}
export DB_ROOT_PASS=${DB_ROOT_PASS:-root}

# Start supervisord using conda
exec conda run --no-capture-output -n myenv /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf