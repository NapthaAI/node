#!/bin/bash

# Name of the Docker container
CONTAINER_NAME="naptha-container"

# Stop the container
echo "Stopping container..."
docker stop $CONTAINER_NAME

# Remove the container
echo "Removing container..."
docker rm $CONTAINER_NAME

echo "Container stopped and removed."