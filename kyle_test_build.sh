#!/bin/zsh
ACCOUNT="kmistele"
REPOSITORY="naptha-node-test"
CUDA_BASE_IMAGE="nvidia/cuda:12.4.1-devel-ubuntu22.04"

COMMIT_HASH=$(git rev-parse HEAD | cut -c1-7)

# TODO port this into a github actions workflow matrix...

echo "Building standard CPU images..."
docker buildx build \
  --platform linux/arm64,linux/amd64 \
  -t $ACCOUNT/$REPOSITORY:latest \
  -t $ACCOUNT/$REPOSITORY:COMMIT_HASH \
  -t $ACCOUNT/$REPOSITORY:cpu-latest \
  -t $ACCOUNT/$REPOSITORY:cpu-COMMIT_HASH \
  -f buildx.Dockerfile \
  --push .


#echo "building CUDA images..."
#docker buildx build \
#  --platform linux/arm64,linux/amd64 \
#  --build-arg BASE_IMAGE=$CUDA_BASE_IMAGE \
#  -t $ACCOUNT/$REPOSITORY:cuda-latest \
#  -t $ACCOUNT/$REPOSITORY:cuda-COMMIT_HASH \
#  -f buildx.Dockerfile \
#  --push .