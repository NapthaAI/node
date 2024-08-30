#!/bin/bash

# Source the .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | awk '/=/ {print $1}')
else
    echo ".env file not found"
    exit 1
fi

# Name of the Docker image
IMAGE_NAME="naptha-full-stack"

# Name of the Docker container
CONTAINER_NAME="naptha-container"

# Detect the operating system and choose the appropriate Dockerfile
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    DOCKERFILE="Dockerfile.macos"
    echo "Detected macOS. Using $DOCKERFILE"
else
    # Linux or other
    if [ "$GPU" = "true" ]; then
        DOCKERFILE="Dockerfile.linux-gpu"
    else
        DOCKERFILE="Dockerfile.linux-cpu"
    fi
    echo "Using $DOCKERFILE"
fi

# Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME -f $DOCKERFILE . 

# Check if the container already exists
if [ "$(docker ps -aq -f name=$CONTAINER_NAME)" ]; then
    # If it exists, remove it
    echo "Removing existing container..."
    docker rm -f $CONTAINER_NAME
fi

# Ensure the host directories exist, create only if they don't
if [ ! -d "./node/storage/fs" ]; then
    echo "Creating ./node/storage/fs directory..."
    mkdir -p ./node/storage/fs
fi

if [ ! -d "./node/storage/db" ]; then
    echo "Creating ./node/storage/db directory..."
    mkdir -p ./node/storage/db
fi

# if ./logs exists empty it if it does not exist create it
if [ ! -d "./logs" ]; then
    echo "Creating ./logs directory..."
    mkdir -p ./logs
else
    echo "Emptying ./logs directory..."
    sudo rm -rf ./logs/*
fi

chmod 777 ./logs

# if ~/.cache does not exist create it
if [ ! -d "$HOME/.cache" ]; then
    echo "Creating ~/.cache directory..."
    mkdir -p $HOME/.cache
fi

# Run the new container
echo "Starting new container..."
if [ "$GPU" = "true" ]; then
    # GPU version
    docker run -d \
        --gpus all \
        --name $CONTAINER_NAME \
        -p 3002:3002 \
        -p 8000:8000 \
        -p 7001:7001 \
        -p 5672:5672 \
        -p 15672:15672 \
        -p 11434:11434 \
        -v "$(pwd)/node/storage/fs:/app/node/storage/fs" \
        -v "$(pwd)/node/storage/db/db.db:/app/node/storage/db/db.db" \
        -v "$(pwd)/logs:/var/log" \
        -v "$HOME/.cache:/root/.cache" \
        --env-file .env \
        $IMAGE_NAME
else
    # CPU version
    docker run -d \
        --name $CONTAINER_NAME \
        -p 3002:3002 \
        -p 8000:8000 \
        -p 7001:7001 \
        -p 5672:5672 \
        -p 15672:15672 \
        -p 11434:11434 \
        -v "$(pwd)/node/storage/fs:/app/node/storage/fs" \
        -v "$(pwd)/node/storage/db/db.db:/app/node/storage/db/db.db" \
        -v "$(pwd)/logs:/var/log" \
        -v "$HOME/.cache:/root/.cache" \
        --env-file .env \
        $IMAGE_NAME
fi

echo "Container started. You can check its logs with: docker logs $CONTAINER_NAME"