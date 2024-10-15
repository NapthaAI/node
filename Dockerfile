# Use Ubuntu 22.04 as the base image, with an option for CUDA
ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV RABBITMQ_LOG_BASE=/var/log/rabbitmq
ENV PATH="/root/miniforge3/bin:${PATH}"

# Set work directory
WORKDIR /app

# Use ARG to determine if we're building for GPU
ARG USE_GPU=false
ARG OS_TYPE=linux

# Install system dependencies, build tools, and networking utilities
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    lsb-release \
    supervisor \
    gcc-12 \
    g++-12 \
    python3-dev \
    net-tools \  
    psmisc \     
    lsof \  
    iproute2 \
    libnuma-dev \
    wget \
    git \
    cmake \
    ninja-build \
    libtcmalloc-minimal4 \
    && update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-12 10 --slave /usr/bin/g++ g++ /usr/bin/g++-12 \
    && rm -rf /var/lib/apt/lists/*

# Install Miniforge
RUN if [ "$OS_TYPE" = "linux" ]; then \
        wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -O miniforge.sh; \
    elif [ "$OS_TYPE" = "macos" ]; then \
        wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh -O miniforge.sh; \
    fi && \
    bash miniforge.sh -b -p $HOME/miniforge3 && \
    rm miniforge.sh

# Add conda to PATH
RUN echo "source $HOME/miniforge3/etc/profile.d/conda.sh" >> ~/.bashrc && \
    echo "conda activate base" >> ~/.bashrc

# Install SurrealDB
RUN curl -sSf https://install.surrealdb.com | sh

# Install RabbitMQ and Erlang
RUN if [ "$OS_TYPE" = "linux" ]; then \
        curl -1sLf "https://dl.cloudsmith.io/public/rabbitmq/rabbitmq-erlang/setup.deb.sh" | bash && \
        curl -1sLf "https://dl.cloudsmith.io/public/rabbitmq/rabbitmq-server/setup.deb.sh" | bash && \
        apt-get update && \
        apt-get install -y erlang-base \
                           erlang-asn1 erlang-crypto erlang-eldap erlang-ftp erlang-inets \
                           erlang-mnesia erlang-os-mon erlang-parsetools erlang-public-key \
                           erlang-runtime-tools erlang-snmp erlang-ssl \
                           erlang-syntax-tools erlang-tftp erlang-tools erlang-xmerl \
                           rabbitmq-server; \
    elif [ "$OS_TYPE" = "macos" ]; then \
        apt-get update && \
        apt-get install -y erlang-base \
                           erlang-asn1 erlang-crypto erlang-eldap erlang-ftp erlang-inets \
                           erlang-mnesia erlang-os-mon erlang-parsetools erlang-public-key \
                           erlang-runtime-tools erlang-snmp erlang-ssl \
                           erlang-syntax-tools erlang-tftp erlang-tools erlang-xmerl \
                           rabbitmq-server; \
    fi && \
    rm -rf /var/lib/apt/lists/*

# Set up RabbitMQ directories and permissions
RUN mkdir -p /var/log/rabbitmq /var/lib/rabbitmq && \
    chown -R rabbitmq:rabbitmq /var/log/rabbitmq /var/lib/rabbitmq && \
    chmod 777 /var/log/rabbitmq /var/lib/rabbitmq

# Install Ollama
RUN curl https://ollama.ai/install.sh | sh

# Create conda environment with Python 3.12
RUN conda create -n myenv python=3.12 -y

# Activate conda environment
SHELL ["conda", "run", "-n", "myenv", "/bin/bash", "-c"]

# Install poetry
RUN pip install poetry

# Install vLLM dependencies based on GPU flag and OS type
RUN if [ "$OS_TYPE" = "macos" ]; then \
        pip install -vv poetry; \
    elif [ "$USE_GPU" = "true" ]; then \
        pip install -vv vllm poetry; \
    else \
        pip install -vv poetry && \
        pip install intel-openmp && \
        pip install --upgrade pip && \
        pip install cmake>=3.26 wheel packaging ninja "setuptools-scm>=8" numpy && \
        git clone -b rls-v3.5 https://github.com/oneapi-src/oneDNN.git && \
        cmake -B ./oneDNN/build -S ./oneDNN -G Ninja -DONEDNN_LIBRARY_TYPE=STATIC \
            -DONEDNN_BUILD_DOC=OFF \
            -DONEDNN_BUILD_EXAMPLES=OFF \
            -DONEDNN_BUILD_TESTS=OFF \
            -DONEDNN_BUILD_GRAPH=OFF \
            -DONEDNN_ENABLE_WORKLOAD=INFERENCE \
            -DONEDNN_ENABLE_PRIMITIVE=MATMUL && \
        cmake --build ./oneDNN/build --target install --config Release && \
        git clone https://github.com/vllm-project/vllm.git /app/vllm && \
        cd /app/vllm && \
        pip install -v -r requirements-cpu.txt --extra-index-url https://download.pytorch.org/whl/cpu && \
        VLLM_TARGET_DEVICE=cpu python setup.py install && \
        cd /app; \
    fi

# Set LD_PRELOAD for tcmalloc
ENV LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4"

# Copy the project files
COPY ./.dockerignore /app/
COPY ./node /app/node
COPY ./celery_worker_start_docker.sh /app/
COPY ./environment.yml /app/
COPY ./init_llm.py /app/
COPY ./setup_venv.sh /app/
COPY ./supervisord.conf /app/
COPY ./pyproject.toml /app/
COPY ./poetry.lock /app/
COPY ./README.md /app/
COPY ./start.sh /app/
COPY ./init_rabbitmq.sh /app/

RUN chmod +x /app/init_rabbitmq.sh

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
EXPOSE 3001 3002 7001 7002 5672 15672 11434 

# Expose ssh
EXPOSE 22

# Set up supervisord configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy the start script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Set the entrypoint to the start script
ENTRYPOINT ["/app/start.sh"]
