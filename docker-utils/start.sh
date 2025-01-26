#!/bin/bash

# Set default values for environment variables
export RMQ_USER=${RMQ_USER:-username}
export RMQ_PASSWORD=${RMQ_PASSWORD:-password}
export IN_DOCKER=${IN_DOCKER:-true}
export STABILITY_API_KEY=${STABILITY_API_KEY:-sk-}
export OPENAI_API_KEY=${OPENAI_API_KEY:-sk-}
export LOCAL_DB_POSTGRES_PORT=${LOCAL_DB_POSTGRES_PORT:-3002}
export LOCAL_DB_POSTGRES_USERNAME=${LOCAL_DB_POSTGRES_USERNAME:-naptha}
export LOCAL_DB_POSTGRES_PASSWORD=${LOCAL_DB_POSTGRES_PASSWORD:-napthapassword}
export LOCAL_DB_POSTGRES_NAME=${LOCAL_DB_POSTGRES_NAME:-naptha}
export HUB_DB_SURREAL_PORT=${HUB_DB_SURREAL_PORT:-3001}
export HUB_DB_SURREAL_NS=${HUB_DB_SURREAL_NS:-naptha}
export HUB_DB_SURREAL_NAME=${HUB_DB_SURREAL_NAME:-naptha}
export HUB_USERNAME=${HUB_USERNAME:-username}
export HUB_PASSWORD=${HUB_PASSWORD:-password}

# Start supervisord using conda
exec conda run --no-capture-output -n myenv /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf