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

# this will be the base image either the ubuntu or the cuda one
ENV BASE_IMAGE=${BASE_IMAGE}

# this will be the value / one of the values of the `--platform` argument
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
RUN if [ "$PLATFORM" = "linux/amd64" ]; then \
        wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -O miniforge.sh; \
    elif [ "$PLATFORM" = "linux/arm64" ]; then \
        wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh -O miniforge.sh; \
    else \
        echo "Unsupported platform: $PLATFORM. Only linux/amd64 and linux/arm64 are supported." && exit 1; \
    fi && \
    bash miniforge.sh -b -p $HOME/miniforge3 && \
    rm miniforge.sh

# Add conda to PATH
RUN echo "source $HOME/miniforge3/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc

# install RabbitMQ - no conditional needed here unlike the host containe
RUN curl -1sLf "https://dl.cloudsmith.io/public/rabbitmq/rabbitmq-erlang/setup.deb.sh" | bash && \
    curl -1sLf "https://dl.cloudsmith.io/public/rabbitmq/rabbitmq-server/setup.deb.sh" | bash && \
    apt-get update && \
    apt-get install -y erlang-base \
                       erlang-asn1 erlang-crypto erlang-eldap erlang-ftp erlang-inets \
                       erlang-mnesia erlang-os-mon erlang-parsetools erlang-public-key \
                       erlang-runtime-tools erlang-snmp erlang-ssl \
                       erlang-syntax-tools erlang-tftp erlang-tools erlang-xmerl \
                       rabbitmq-server

RUN echo "Running on $PLATFORM (image: $BASE_IMAGE)"

