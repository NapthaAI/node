#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fuction to clean the node
clean_node() {
    # Remove node/modules
    rm -rf node/modules

    # make pyproject-clean
    make pyproject-clean

    # poetry lock
    poetry lock

    # poetry install
    poetry install
}

# Function for prefixed logging
log_with_service_name() {
    local service_name=$1
    local color=$2
    while IFS= read -r line; do
        printf "%b[%s]%b %s\n" "$color" "$service_name" "$NC" "$line"
    done
}

# Function to check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        echo "Docker does not seem to be running, please start Docker first." | log_with_service_name "Docker" $RED
    fi
}

# Function to start RabbitMQ in Docker
start_rabbitmq() {
    # Check if RabbitMQ container exists and is running
    if docker ps --filter "name=rabbitmq" --filter "status=running" | grep -q rabbitmq; then
        echo "RabbitMQ is already running." | log_with_service_name "RabbitMQ" $GREEN
        return
    fi

    # Check if RabbitMQ container exists but stopped
    if docker ps --all --filter "name=rabbitmq" | grep -q rabbitmq; then
        echo "RabbitMQ container exists but stopped. Starting it..." | log_with_service_name "RabbitMQ" $GREEN
        docker start rabbitmq
    else
        echo "Starting RabbitMQ in Docker..." | log_with_service_name "RabbitMQ" $GREEN
        docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
    fi

    # Wait for RabbitMQ to start
    until docker exec rabbitmq rabbitmqctl list_queues >/dev/null 2>&1; do
        echo "Waiting for RabbitMQ to start..." | log_with_service_name "RabbitMQ" $GREEN
        sleep 1
    done
}

start_node() {
    # Install Poetry if it's not already installed
    command -v poetry >/dev/null 2>&1 || {
        echo "Installing Poetry..." | log_with_service_name "Hub" $BLUE
        curl -sSL https://install.python-poetry.org | python
        
        # Find the Poetry executable and get its directory
        POETRY_PATH=$(find $HOME -name poetry -type f 2>/dev/null | sed 's|/poetry||' | head -n 1)

        if [ -n "$POETRY_PATH" ]; then
            # Add Poetry to PATH for current session
            export PATH="$POETRY_PATH:$PATH"
            echo "Poetry path added to PATH for current session: $POETRY_PATH"

            # Add Poetry to PATH permanently in .bashrc
            echo "export PATH=\"$POETRY_PATH:\$PATH\"" >> ~/.bashrc
            echo "Poetry path added to .bashrc for permanent effect."
        else
            echo "Poetry executable not found."
        fi
    }

    # Load .env file
    set -a
    if [ -f .env ]; then
        source .env
    else
        echo ".env file does not exist"
    fi
    set +a

    # Get the port from the .env file
    port=${NODE_PORT}
    echo "Using $port for Node" | log_with_service_name "Node" $GREEN

    # Check if the port is already in use
    if lsof -i :$port >/dev/null; then
        echo "Port $port is already in use. Please stop the application running on this port and try again." | log_with_service_name "Node" $GREEN
    fi

    # Change to the project directory
    cd node

    # Configure Poetry to create a virtual environment in the project directory
    poetry config virtualenvs.in-project true

    # Install dependencies and create the virtual environment
    poetry install

    echo "Starting Node application..." | log_with_service_name "Node" $GREEN

    # Run the Python script using the Poetry's virtual environment
    poetry run python main.py 2>&1 | log_with_service_name "Node" $GREEN &

    # Change back to the original directory (if needed)
    cd -

    until curl -s localhost:$port >/dev/null 2>&1; do
        echo "Waiting for Node application to start..." | log_with_service_name "Node" $GREEN
        sleep 1
    done
}

# Function to start the Celery worker
start_celery_worker() {
    echo "Starting Celery worker..." | log_with_service_name "Celery" $RED

    # Activate the virtual environment
    . .venv/bin/activate

    # Start the Celery worker
    celery -A node.celery_worker.celery_worker.app worker --loglevel=info 2>&1 | log_with_service_name "Celery" $RED &

    # Check until the Celery worker is up and running
    until docker exec rabbitmq rabbitmqctl list_queues | grep -q celery; do
        echo "Waiting for Celery worker to start..." | log_with_service_name "Celery" $RED
        sleep 1
    done
}

# Function to install Miniforge
install_miniforge() {
    # Check if Miniforge is already installed
    if [ -d "$HOME/miniforge3" ]; then
        echo "Miniforge is already installed." | log_with_service_name "Miniforge" $GREEN
        return
    fi

    echo "Installing Miniforge..." | log_with_service_name "Miniforge" $GREEN

    # Define Miniforge installer file
    MINIFORGE_INSTALLER="Miniforge3-Linux-x86_64.sh"

    # Download the Miniforge installer
    curl -sSL "https://github.com/conda-forge/miniforge/releases/latest/download/$MINIFORGE_INSTALLER" -o $MINIFORGE_INSTALLER

    # Make the installer executable
    chmod +x $MINIFORGE_INSTALLER

    # Run the Miniforge installer
    ./$MINIFORGE_INSTALLER -b

    # Remove the installer file
    rm $MINIFORGE_INSTALLER

    # Initialize conda for bash shell
    "$HOME/miniforge3/bin/conda" init bash

    # Check if Miniforge and conda are installed correctly
    if [ -d "$HOME/miniforge3" ] && [ -x "$HOME/miniforge3/bin/conda" ]; then
        echo "Miniforge installed successfully." | log_with_service_name "Miniforge" $GREEN
    else
        echo "Miniforge installation failed." | log_with_service_name "Miniforge" $RED
    fi

    # Reload the shell configuration
    . ~/.bashrc
}

# Function to install SurrealDB
install_surrealdb() {
    # Define the installation path
    SURREALDB_INSTALL_PATH="/home/ubuntu/.surrealdb"
    SURREALDB_BINARY="$SURREALDB_INSTALL_PATH/surreal"

    # check /usr/local/bin/surreal exists
    if [ -f /usr/local/bin/surreal ]; then
        echo "SurrealDB is already installed." | log_with_service_name "SurrealDB" $GREEN
        return
    fi

    echo "Installing SurrealDB..." | log_with_service_name "SurrealDB" $GREEN

    # Install SurrealDB
    curl -sSf https://install.surrealdb.com | sh

    # Option 1: Add the installation path to .bashrc
    # echo "export PATH=\"$SURREALDB_INSTALL_PATH:\$PATH\"" >> ~/.bashrc
    # echo "SurrealDB path added to .bashrc. Please restart your shell or source .bashrc to apply changes."

    # Option 2: Move the binary to /usr/local/bin
    if [ -f "$SURREALDB_BINARY" ]; then
        sudo mv "$SURREALDB_BINARY" /usr/local/bin/surreal
        echo "SurrealDB binary moved to /usr/local/bin."
    else
        echo "SurrealDB installation failed." | log_with_service_name "SurrealDB" $RED
    fi
}

# Function for manual installation of Ollama
install_ollama() {
    if command -v ollama >/dev/null 2>&1; then
        echo "Ollama is already installed." | log_with_service_name "Ollama" $GREEN
        return
    else
        echo "Installing Ollama..." | log_with_service_name "Ollama" $GREEN
        sudo curl -L https://ollama.ai/download/ollama-linux-amd64 -o /usr/bin/ollama
        sudo chmod +x /usr/bin/ollama

        sudo useradd -r -s /bin/false -m -d /usr/share/ollama ollama

        sudo cp ./ops/systemd/ollama.service /etc/systemd/system/

        sudo systemctl daemon-reload
        sudo systemctl enable ollama

        echo "Ollama installed successfully." | log_with_service_name "Ollama" $GREEN
    fi
}

# Main execution flow
install_miniforge
install_surrealdb
install_ollama
check_docker
start_rabbitmq
clean_node
start_node
start_celery_worker

echo "Setup complete. Applications are running." | log_with_service_name "System" $GREEN

# Keep the script running to maintain background processes
wait
