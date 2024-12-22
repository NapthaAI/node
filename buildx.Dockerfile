# use default ubuntu as the base image, but you can specify an image like nvidia/cuda:12.4.1-devel-ubuntu22.04 for CUDA
ARG BASE_IMAGE=ubuntu:24.04

#################### BASE BUILD IMAGE ####################
# prepare basic build environment
FROM ${BASE_IMAGE}
ARG TARGETPLATFORM
ARG BASE_IMAGE=ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV RABBITMQ_LOG_BASE=/var/log/rabbitmq
ENV PATH="/root/miniforge3/bin:${PATH}"

# for configuring installations based on CPU and if cuda should be enabled
ENV BASE_IMAGE=${BASE_IMAGE}
ENV PLATFORM=${TARGETPLATFORM}

# Set work directory
WORKDIR /app

# Install system dependencies, build tools, and networking utilities
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    lsb-release \
    supervisor \
    gcc \
    g++ \
    python3-dev \
    net-tools \
    psmisc \
    lsof \
    iproute2 \
    libnuma-dev \
    wget \
    git \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Install miniforge based on the target platform \
CMD echo $PLATFORM running on $BASE_IMAGE