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
RUN apt update -y
RUN apt install curl software-properties-common apt-transport-https lsb-release -y
RUN curl -1sLf 'https://dl.cloudsmith.io/public/rabbitmq/rabbitmq-erlang/setup.deb.sh' | bash
RUN apt update -y
RUN apt-get install -y erlang-base \
                        erlang-asn1 erlang-crypto erlang-eldap erlang-ftp erlang-inets \
                        erlang-mnesia erlang-os-mon erlang-parsetools erlang-public-key \
                        erlang-runtime-tools erlang-snmp erlang-ssl \
                        erlang-syntax-tools erlang-tftp erlang-tools erlang-xmerl

## Install rabbitmq-server and its dependencies
RUN apt-get install rabbitmq-server -y --fix-missing

# Set up RabbitMQ directories and permissions
RUN mkdir -p /var/log/rabbitmq /var/lib/rabbitmq && \
    chown -R rabbitmq:rabbitmq /var/log/rabbitmq /var/lib/rabbitmq && \
    chmod 777 /var/log/rabbitmq /var/lib/rabbitmq

# Install Ollama
RUN curl https://ollama.ai/install.sh | sh

RUN sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list' && \
    wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - && \
    apt-get update && \
    apt-get install -y postgresql-16 postgresql-contrib-16 && \
    # Clean up and initialize PostgreSQL data directory
    rm -rf /var/lib/postgresql/16/main && \
    mkdir -p /var/lib/postgresql/16/main && \
    chown postgres:postgres /var/lib/postgresql/16/main && \
    su - postgres -c "/usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/16/main" && \
    # Configure PostgreSQL
    sed -i "s/#port = .*/port = 3002/" /etc/postgresql/16/main/postgresql.conf && \
    sed -i "s/#listen_addresses = .*/listen_addresses = '*'/" /etc/postgresql/16/main/postgresql.conf && \
    echo "host    all             all             0.0.0.0/0               md5" >> /etc/postgresql/16/main/pg_hba.conf;

# Set permissions for PostgreSQL directories
RUN mkdir -p /var/log/postgresql && \
    chown -R postgres:postgres /var/log/postgresql && \
    chmod -R 777 /var/log/postgresql && \
    chown -R postgres:postgres /var/lib/postgresql && \
    chmod -R 700 /var/lib/postgresql/16/main

# Create conda environment with Python 3.12
RUN conda create -n myenv python=3.12 -y

# Activate conda environment
SHELL ["conda", "run", "-n", "myenv", "/bin/bash", "-c"]

RUN pip install -vv poetry

# Copy the project files
COPY ./docker-utils/.dockerignore /app/
COPY ./docker-utils/celery_worker_start_docker.sh /app/
COPY ./docker-utils/environment.yml /app/
COPY ./docker-utils/init_llm.py /app/
COPY ./docker-utils/setup_venv.sh /app/
COPY ./docker-utils/supervisord.conf /app/
COPY ./docker-utils/start.sh /app/
COPY ./node /app/node
COPY ./pyproject.toml /app/
COPY ./poetry.lock /app/
COPY ./README.md /app/

# After copying all files
WORKDIR /app

# Run the setup script
RUN chmod +x /app/setup_venv.sh
RUN /bin/bash -c "source $HOME/.profile && /app/setup_venv.sh"

# Create log directory and files
RUN mkdir -p /var/log && \
    touch /var/log/supervisord.log && \
    touch /var/log/rabbitmq.log && \
    touch /var/log/rabbitmq.err.log && \
    touch /var/log/ollama.log && \
    touch /var/log/ollama.err.log && \
    touch /var/log/vllm.log && \
    touch /var/log/vllm.err.log && \
    touch /var/log/gateway.log && \
    touch /var/log/gateway.err.log && \
    touch /var/log/celery.log && \
    touch /var/log/celery.err.log && \
    touch /var/log/llm_backend.log && \
    touch /var/log/llm_backend.err.log && \
    touch /var/log/ollama.err.log && \
    touch /var/log/ollama.log && \
    chmod 666 /var/log/*.log

# Expose ports
EXPOSE 3001 3002 7001 7002 5672 15672 11434 22

# Set up supervisord configuration
COPY ./docker-utils/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy the start script
COPY ./docker-utils/start.sh /app/start.sh
RUN chmod +x /app/start.sh

COPY ./docker-utils/init_postgres.sh /app/init_postgres.sh
RUN chmod +x /app/init_postgres.sh

# Set the entrypoint to the start script
ENTRYPOINT ["/app/start.sh"]