#!/bin/bash

# Set default values for environment variables
export RMQ_USER=${RMQ_USER:-username}
export RMQ_PASSWORD=${RMQ_PASSWORD:-password}
export IN_DOCKER=${IN_DOCKER:-true}
export STABILITY_API_KEY=${STABILITY_API_KEY:-sk-}
export OPENAI_API_KEY=${OPENAI_API_KEY:-sk-}
export LOCAL_DB_PORT=${LOCAL_DB_PORT:-3002}
export LOCAL_DB_USER=${LOCAL_DB_USER:-naptha}
export LOCAL_DB_PASSWORD=${LOCAL_DB_PASSWORD:-napthapassword}
export LOCAL_DB_NAME=${LOCAL_DB_NAME:-naptha}
export HUB_DB_PORT=${HUB_DB_PORT:-3001}
export HUB_NS=${HUB_NS:-naptha}
export HUB_DB=${HUB_DB:-naptha}
export HUB_USERNAME=${HUB_USERNAME:-username}
export HUB_PASSWORD=${HUB_PASSWORD:-password}

# Start supervisord using conda
exec conda run --no-capture-output -n myenv /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf