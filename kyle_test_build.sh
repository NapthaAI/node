#!/bin/sh
ACCOUNT="kmistele";
REPOSITORY="naptha-node-test";
CUDA_BASE_IMAGE="nvidia/cuda:12.4.1-devel-ubuntu22.04"

echo "repository: $REPOSITORY"
echo "Full repository: $ACCOUNT/$REPOSITORY:latest"
COMMIT_HASH=$(git rev-parse HEAD | cut -c1-7)


# TODO port this into a github actions workflow matrix...
set -x
echo "Building standard CPU images..."
COMMIT_HASH=$(git rev-parse HEAD | cut -c1-7)
DOCKER_BUILDKIT=1 docker buildx build \
  --progress=plain \
  --platform linux/arm64,linux/amd64 \
  -t "kmistele/naptha-node-test:latest" \
  -t "kmistele/naptha-node-test:$COMMIT_HASH" \
  -t "kmistele/naptha-node-test:cpu-latest" \
  -t "kmistele/naptha-node-test:cpu-$COMMIT_HASH" \
  -f buildx.Dockerfile \
  --push \
  . --no-cache


DOCKER_BUILDKIT=1 docker buildx build \
  --progress=plain \
  --platform linux/arm64,linux/amd64 \
  -t "kmistele/naptha-node-test:cuda-latest" \
  -t "kmistele/naptha-node-test:cuda-$COMMIT_HASH" \
  -f buildx.Dockerfile \
  --push \
  --build-arg BASE_IMAGE=$CUDA_BASE_IMAGE \
  . --no-cache
