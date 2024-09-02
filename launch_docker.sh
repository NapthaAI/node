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

# Detect the operating system and set build arguments
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    BASE_IMAGE="ubuntu:24.04"
    BUILD_ARGS="--build-arg BASE_IMAGE=${BASE_IMAGE} --build-arg USE_GPU=false --build-arg OS_TYPE=macos"
    echo "Detected macOS. Using base image: $BASE_IMAGE"
    
    # Ensure LLM_BACKEND is set to 'ollama' for macOS
    if [ "$LLM_BACKEND" != "ollama" ]; then
        echo "Setting LLM_BACKEND to 'ollama' for macOS"
        sed -i '' 's/^LLM_BACKEND=.*/LLM_BACKEND=ollama/' .env
    fi
    
    # Ensure OLLAMA_MODELS is set
    if [ -z "$OLLAMA_MODELS" ]; then
        echo "OLLAMA_MODELS is not set. Please enter the Ollama models you want to use (comma-separated if multiple):"
        read OLLAMA_MODELS
        echo "OLLAMA_MODELS=$OLLAMA_MODELS" >> .env
    fi
else
    # Linux
    if [ "$GPU" = "true" ]; then
        BASE_IMAGE="nvidia/cuda:12.2.0-base-ubuntu22.04"
        BUILD_ARGS="--build-arg BASE_IMAGE=${BASE_IMAGE} --build-arg USE_GPU=true --build-arg OS_TYPE=linux"
    else
        BASE_IMAGE="ubuntu:24.04"
        BUILD_ARGS="--build-arg BASE_IMAGE=${BASE_IMAGE} --build-arg USE_GPU=false --build-arg OS_TYPE=linux"
    fi
    echo "Detected Linux. Using base image: $BASE_IMAGE"
fi

echo "Building Docker image with ARGS: $BUILD_ARGS"

# Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME $BUILD_ARGS .

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

# if ./logs exists empty it, if it does not exist create it
if [ ! -d "./logs" ]; then
    echo "Creating ./logs directory..."
    mkdir -p ./logs
else
    echo "Emptying ./logs directory..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        rm -rf ./logs/*
    else
        sudo rm -rf ./logs/*
    fi
fi

chmod 777 ./logs

# if ~/.cache does not exist create it
if [ ! -d "$HOME/.cache" ]; then
    echo "Creating ~/.cache directory..."
    mkdir -p $HOME/.cache
fi

# Run the new container
echo "Starting new container..."
if [ "$GPU" = "true" ] && [[ "$OSTYPE" != "darwin"* ]]; then
    # GPU version (Linux only)
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
    # CPU version (Linux and macOS)
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