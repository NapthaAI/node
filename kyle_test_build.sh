#!/bin/zsh
ACCOUNT="kmistele"
REPOSITORY="naptha-node-test"
CUDA_BASE_IMAGE="nvidia/cuda:12.4.1-devel-ubuntu22.04"

echo "Building standard CPU images..."
docker buildx build \
  --platform linux/arm64,linux/amd64 \
  -t $ACCOUNT/$REPOSITORY:latest \
  -f buildx.Dockerfile \
  --push .

echo "building CUDA images..."
docker buildx build \
  --platform linux/arm64,linux/amd64 \
  --build-arg BASE_IMAGE=$CUDA_BASE_IMAGE \
  -t $ACCOUNT/$REPOSITORY:cuda-latest \
  -f buildx.Dockerfile \
  --push .