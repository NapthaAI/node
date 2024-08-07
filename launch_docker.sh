#!/bin/bash

# Name of the Docker image
IMAGE_NAME="naptha-full-stack"

# Name of the Docker container
CONTAINER_NAME="naptha-container"

# Build the Docker image
echo "Building Docker image..."
docker build -t $IMAGE_NAME . --no-cache

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

# Run the new container
echo "Starting new container..."
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
    --env-file .env \
    $IMAGE_NAME
echo "Container started. You can check its logs with: docker logs $CONTAINER_NAME"