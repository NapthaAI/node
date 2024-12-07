#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PINK='\033[0;35m'
NC='\033[0m'

# Function for prefixed logging
log_with_service_name() {
    local service_name=$1
    local color=$2
    while IFS= read -r line; do
        echo -e "${color}[$service_name]${NC} $line"
    done
}

get_surrealdb_version() {
    surreal -V | awk '{print $6}'
}

install_surrealdb() {
    echo "Installing SurrealDB..." | log_with_service_name "SurrealDB" $GREEN

    if [ "$os" = "Darwin" ]; then
        SURREALDB_INSTALL_PATH="/Users/$(whoami)/.surrealdb"
    else
        SURREALDB_INSTALL_PATH="/home/$(whoami)/.surrealdb"
    fi
    SURREALDB_BINARY="$SURREALDB_INSTALL_PATH/surreal"

    # Check if SurrealDB is already installed
    if [ -f /usr/local/bin/surreal ]; then
        CURRENT_VERSION=$(get_surrealdb_version)
        if [[ $CURRENT_VERSION == 2.* ]]; then
            echo "SurrealDB version 2 ($CURRENT_VERSION) is already installed." | log_with_service_name "SurrealDB" $GREEN
            return
        else
            echo "Removing existing SurrealDB version $CURRENT_VERSION..." | log_with_service_name "SurrealDB" $YELLOW
            sudo rm /usr/local/bin/surreal
        fi
    fi

    echo "Installing SurrealDB version 2..." | log_with_service_name "SurrealDB" $GREEN

    # Install SurrealDB
    curl -sSf https://install.surrealdb.com | sh

    if [ -f "$SURREALDB_BINARY" ]; then
        echo "Moving SurrealDB binary to /usr/local/bin..." | log_with_service_name "SurrealDB" $GREEN
        sudo mv "$SURREALDB_BINARY" /usr/local/bin/surreal
        if [ $? -ne 0 ]; then
            echo "Failed to move SurrealDB binary. Trying to copy instead..." | log_with_service_name "SurrealDB" $YELLOW
            sudo cp "$SURREALDB_BINARY" /usr/local/bin/surreal
            if [ $? -ne 0 ]; then
                echo "Failed to copy SurrealDB binary. Installation failed." | log_with_service_name "SurrealDB" $RED
                exit 1
            fi
        fi
        echo "SurrealDB binary installed in /usr/local/bin." | log_with_service_name "SurrealDB" $GREEN
    else
        echo "SurrealDB binary not found at $SURREALDB_BINARY. Installation may have failed." | log_with_service_name "SurrealDB" $RED
        exit 1
    fi

    # Verify installed version
    if command -v surreal &> /dev/null; then
        INSTALLED_VERSION=$(get_surrealdb_version)
        if [[ $INSTALLED_VERSION == 2.* ]]; then
            echo "SurrealDB version 2 ($INSTALLED_VERSION) installed successfully." | log_with_service_name "SurrealDB" $GREEN
        else
            echo "Failed to install SurrealDB version 2. Got version: $INSTALLED_VERSION" | log_with_service_name "SurrealDB" $RED
            exit 1
        fi
    else
        echo "SurrealDB command not found. Installation failed." | log_with_service_name "SurrealDB" $RED
        exit 1
    fi
}

# Function for manual installation of Ollama
linux_install_ollama() {
    set -a
    source .env
    set +a

    # Echo start Ollama
    echo "Installing Ollama..." | log_with_service_name "Ollama" $RED

    if command -v ollama >/dev/null 2>&1; then
        echo "Ollama is already installed." | log_with_service_name "Ollama" $RED
        sudo cp ./ops/systemd/ollama.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable ollama
        sudo systemctl start ollama
    else
        echo "Installing Ollama..." | log_with_service_name "Ollama" $RED
        sudo curl -L https://ollama.ai/download/ollama-linux-amd64 -o /usr/bin/ollama
        sudo chmod +x /usr/bin/ollama
        sudo useradd -r -s /bin/false -m -d /usr/share/ollama ollama
        sudo cp ./ops/systemd/ollama.service /etc/systemd/system/
        sudo systemctl daemon-reload
        sudo systemctl enable ollama
        sudo systemctl start ollama
        echo "Ollama installed successfully." | log_with_service_name "Ollama" $RED
    fi
    # Pull Ollama models
    echo "Pulling Ollama models: $OLLAMA_MODELS" | log_with_service_name "Ollama" $RED
    for model in $OLLAMA_MODELS; do
        echo "Pulling model: $model" | log_with_service_name "Ollama" $RED
        ollama pull "$model"
    done
}

darwin_install_ollama() {
    set -a
    source .env
    set +a
    
    # Echo start Ollama
    echo "Installing Ollama..." | log_with_service_name "Ollama" $RED

    if command -v ollama >/dev/null 2>&1; then
        echo "Ollama is already installed." | log_with_service_name "Ollama" $RED
        cp ./ops/launchd/ollama.plist ~/Library/LaunchAgents/
        launchctl load ~/Library/LaunchAgents/com.example.ollama.plist
    else
        echo "Installing Ollama..." | log_with_service_name "Ollama" $RED
        sudo curl -L https://ollama.ai/download/ollama-linux-amd64 -o /usr/bin/ollama
        sudo chmod +x /usr/bin/ollama
        sudo dscl . -create /Users/ollama
        sudo dscl . -create /Users/ollama UserShell /bin/false
        sudo dscl . -create /Users/ollama NFSHomeDirectory /usr/share/ollama
        cp ./ops/launchd/ollama.plist ~/Library/LaunchAgents/
        launchctl load ~/Library/LaunchAgents/com.example.ollama.plist
        echo "Ollama installed successfully." | log_with_service_name "Ollama" $RED
    fi
    ollama serve &
    sleep 1
    # Pull Ollama models
    echo "Pulling Ollama models: $OLLAMA_MODELS" | log_with_service_name "Ollama" $RED
    IFS=',' read -ra MODELS <<< "$OLLAMA_MODELS"
    echo "MODELS: $MODELS" | log_with_service_name "Ollama" $RED
    for model in "${MODELS[@]}"; do
        echo "Pulling model: $model" | log_with_service_name "Ollama" $RED
        ollama pull "$model"
    done
}

# Function to install Miniforge
linux_install_miniforge() {
    
    echo "Checking for Miniforge installation..." | log_with_service_name "Miniforge" $BLUE

    # Check if Miniforge is already installed
    if [ -d "$HOME/miniforge3" ]; then
        echo "Miniforge is already installed." | log_with_service_name "Miniforge" $BLUE
    else
        # Installation process
        echo "Installing Miniforge..." | log_with_service_name "Miniforge" $BLUE
        MINIFORGE_INSTALLER="Miniforge3-Linux-x86_64.sh"
        curl -sSL "https://github.com/conda-forge/miniforge/releases/latest/download/$MINIFORGE_INSTALLER" -o $MINIFORGE_INSTALLER
        chmod +x $MINIFORGE_INSTALLER
        ./$MINIFORGE_INSTALLER -b
        rm $MINIFORGE_INSTALLER
        "$HOME/miniforge3/bin/conda" init bash
    fi

    # Ensure Miniforge's bin directory is in PATH in .bashrc
    if ! grep -q 'miniforge3/bin' ~/.bashrc; then
        echo 'export PATH="$HOME/miniforge3/bin:$PATH"' >> ~/.bashrc
        source ~/.bashrc
        echo "Miniforge path added to .bashrc" | log_with_service_name "Miniforge" $BLUE
    fi

    # Activate Miniforge environment
    eval "$($HOME/miniforge3/bin/conda shell.bash hook)"
    conda activate

    # Check which Python is in use
    PYTHON_PATH=$(which python)
    if [[ $PYTHON_PATH == *"$HOME/miniforge3"* ]]; then
        echo "Miniforge Python is in use." | log_with_service_name "Miniforge" $BLUE
    else
        echo "Miniforge Python is not in use. Activating..." | log_with_service_name "Miniforge" $BLUE
        # Assuming there is a default environment to activate or using base
        conda activate base

        # Check which Python is in use again
        PYTHON_PATH=$(which python)
        echo "Python path: $PYTHON_PATH" | log_with_service_name "Miniforge" $BLUE
    fi
}

darwin_install_miniforge() {
    echo "Checking for Miniforge installation..." | log_with_service_name "Miniforge" $BLUE

    # Check if Miniforge is already installed
    if [ -d "$HOME/miniforge3" ]; then
        echo "Miniforge is already installed." | log_with_service_name "Miniforge" $BLUE
    else
        # Installation process
        echo "Installing Miniforge..." | log_with_service_name "Miniforge" $BLUE
        MINIFORGE_INSTALLER="Miniforge3-MacOSX-arm64.sh"
        curl -sSL "https://github.com/conda-forge/miniforge/releases/latest/download/$MINIFORGE_INSTALLER" -o $MINIFORGE_INSTALLER
        chmod +x $MINIFORGE_INSTALLER
        ./$MINIFORGE_INSTALLER -b
        rm $MINIFORGE_INSTALLER
        "$HOME/miniforge3/bin/conda" init zsh
    fi

    # Ensure Miniforge's bin directory is in PATH in .zshrc
    if ! grep -q 'miniforge3/bin' ~/.zshrc; then
        echo 'export PATH="$HOME/miniforge3/bin:$PATH"' >> ~/.zshrc
        source ~/.zshrc
        echo "Miniforge path added to .zshrc" | log_with_service_name "Miniforge" $BLUE
    fi

    # Activate Miniforge environment
    eval "$($HOME/miniforge3/bin/conda shell.zsh hook)"
    conda activate

    # Check which Python is in use
    PYTHON_PATH=$(which python)
    if [[ $PYTHON_PATH == *"$HOME/miniforge3"* ]]; then
        echo "Miniforge Python is in use." | log_with_service_name "Miniforge" $BLUE
    else
        echo "Miniforge Python is not in use. Activating..." | log_with_service_name "Miniforge" $BLUE
        # Assuming there is a default environment to activate or using base
        conda activate base

        # Check which Python is in use again
        PYTHON_PATH=$(which python)
        echo "Python path: $PYTHON_PATH" | log_with_service_name "Miniforge" $BLUE
    fi
}

# Fuction to clean the node
linux_clean_node() {
    # Eccho start cleaning
    echo "Cleaning node..." | log_with_service_name "Node" $BLUE

    # Remove node/agents if it exists
    if [ -d "node/agents" ]; then
        rm -rf node/agents
    fi

    sudo apt-get install -y make

    # make pyproject-clean
    make pyproject-clean

}

darwin_clean_node() {
    # Echo start cleaning
    echo "Cleaning node..." | log_with_service_name "Node" $BLUE

    # Remove node_modules if it exists
    if [ -d "node_modules" ]; then
        rm -rf node_modules
        echo "Removed node_modules directory." | log_with_service_name "Node" $BLUE
    fi

    # Check if Homebrew is installed
    if ! command -v brew >/dev/null 2>&1; then
        echo "Homebrew not found. Installing Homebrew..." | log_with_service_name "Homebrew" $NC
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi

    # Install make using Homebrew
    if ! command -v make >/dev/null 2>&1; then
        echo "Installing make..." | log_with_service_name "Make" $NC
        brew install make
    else
        echo "Make is already installed." | log_with_service_name "Make" $NC
    fi

    # Run make pyproject-clean
    if [ -f "Makefile" ]; then
        echo "Running make pyproject-clean..." | log_with_service_name "Node" $BLUE
        make pyproject-clean
    else
        echo "Makefile not found. Skipping make pyproject-clean." | log_with_service_name "Node" $BLUE
    fi
}


# Function to check if Docker is running
check_docker() {
    # Echo start checking Docker
    echo "Checking Docker..." | log_with_service_name "Docker" $RED
    if ! docker info >/dev/null 2>&1; then
        echo "Docker does not seem to be running, please start Docker first." | log_with_service_name "Docker" $RED
        exit 1
    fi
}

linux_install_docker() {
    echo "Checking for Docker installation..." | log_with_service_name "Docker" $RED
    
    set -a
    source .env
    set +a

    if [ "$DOCKER_JOBS" = "True" ]; then
        echo "Docker jobs are enabled." | log_with_service_name "Docker" $RED
    else
        echo "Docker jobs are disabled." | log_with_service_name "Docker" $RED
        return
    fi

    if docker >/dev/null 2>&1; then
        echo "Docker is already installed." | log_with_service_name "Docker" $RED
    else
        echo "Installing Docker." | log_with_service_name "Docker" $RED

        sudo apt-get update
        sudo apt-get install ca-certificates curl
        sudo install -m 0755 -d /etc/apt/keyrings
        sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
        sudo chmod a+r /etc/apt/keyrings/docker.asc

        # Add the repository to Apt sources:
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update

        sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

        sudo chmod 666 /var/run/docker.sock

        echo "Docker installed." | log_with_service_name "Docker" $RED
        echo "Starting Docker." | log_with_service_name "Docker" $RED
    fi

    echo "Checking if Docker is running..." | log_with_service_name "Docker" $RED
    if docker info >/dev/null 2>&1; then
        echo "Docker is already running." | log_with_service_name "Docker" $RED
    else
        echo "Starting Docker." | log_with_service_name "Docker" $RED
        sudo systemctl enable docker.service
        sudo systemctl start docker
    fi

    if ! sudo docker info >/dev/null 2>&1; then
        echo "Docker still does not seem to be running. Exiting..." | log_with_service_name "Docker" $RED
        exit 1
    fi    

    echo "Docker is running." | log_with_service_name "Docker" $RED
}

darwin_install_docker() {
    echo "Checking for Docker installation..." | log_with_service_name "Docker" $RED
    
    set -a
    source .env
    set +a

    if [ "$DOCKER_JOBS" = "True" ]; then
        echo "Docker jobs are enabled." | log_with_service_name "Docker" $RED
    else
        echo "DOCKER_JOBS: $DOCKER_JOBS" | log_with_service_name "Docker" $RED
        echo "Docker jobs are disabled." | log_with_service_name "Docker" $RED
        return
    fi

    if docker --version >/dev/null 2>&1; then
        echo "Docker is already installed." | log_with_service_name "Docker" $RED
        
        # Try to start Docker even if it's installed
        echo "Starting Docker..." | log_with_service_name "Docker" $RED
        open -a Docker
    else
        echo "Installing Docker..." | log_with_service_name "Docker" $RED

        if ! command -v brew >/dev/null 2>&1; then
            echo "Homebrew not found. Installing Homebrew..." | log_with_service_name "Homebrew" $NC
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi

        brew install --cask docker
        echo "Docker installed." | log_with_service_name "Docker" $RED
        echo "Starting Docker..." | log_with_service_name "Docker" $RED
        open -a Docker
    fi

    # Wait for Docker to start with timeout
    echo "Waiting for Docker to start..." | log_with_service_name "Docker" $RED
    timeout=60
    start_time=$(date +%s)
    
    while ! docker info >/dev/null 2>&1; do
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $timeout ]; then
            echo "Timeout after ${timeout} seconds waiting for Docker" | log_with_service_name "Docker" $RED
            return 1
        fi
        echo "Still waiting... (${elapsed}s)" | log_with_service_name "Docker" $RED
        sleep 5
    done

    echo "Docker is running." | log_with_service_name "Docker" $RED
    return 0
}

# Function to start RabbitMQ on Linux
linux_start_rabbitmq() {
    echo "Starting RabbitMQ on Linux..." | log_with_service_name "RabbitMQ" $PINK
    # Load the .env file
    set -a
    source .env
    set +a

    # Install RabbitMQ
    sudo apt-get update
    sudo apt-get install -y rabbitmq-server

    # Enable the management plugin
    sudo rabbitmq-plugins enable rabbitmq_management

    # Start RabbitMQ
    sudo systemctl enable rabbitmq-server
    sudo systemctl start rabbitmq-server

    # Check if the user already exists
    if sudo rabbitmqctl list_users | grep -q "^$RMQ_USER"; then
        echo "User '$RMQ_USER' already exists. Skipping user creation."
    else
        # Create a new user with the credentials from .env
        sudo rabbitmqctl add_user "$RMQ_USER" "$RMQ_PASSWORD"
        sudo rabbitmqctl set_user_tags "$RMQ_USER" administrator
        sudo rabbitmqctl set_permissions -p / "$RMQ_USER" ".*" ".*" ".*"
    fi
    echo "RabbitMQ started with management console on default port." | log_with_service_name "RabbitMQ" $PINK
}

# Function to start RabbitMQ on macOS
darwin_start_rabbitmq() {
    echo "Starting RabbitMQ on macOS..." | log_with_service_name "RabbitMQ" $PINK

    # Load the .env file
    set -a
    source .env
    set +a

    # Install RabbitMQ using Homebrew
    brew install rabbitmq

    # Enable the management plugin
    rabbitmq-plugins enable rabbitmq_management

    # Start RabbitMQ
    brew services start rabbitmq

    # Check if the user already exists
    if rabbitmqctl list_users | grep -q "^$RMQ_USER"; then
        echo "User '$RMQ_USER' already exists. Skipping user creation."
    else
        # Create a new user with the credentials from .env
        rabbitmqctl add_user "$RMQ_USER" "$RMQ_PASSWORD"
        rabbitmqctl set_user_tags "$RMQ_USER" administrator
        rabbitmqctl set_permissions -p / "$RMQ_USER" ".*" ".*" ".*"
    fi

    echo "RabbitMQ started with management console on default port." | log_with_service_name "RabbitMQ" $PINK
}

# Function to set up poetry within Miniforge environment
setup_poetry() {
    echo "Setting up Poetry..." | log_with_service_name "Poetry" "$BLUE"
    
    # Ensure the script is running within a Conda environment
    if [ -z "$CONDA_DEFAULT_ENV" ]; then
        echo "Not inside a Conda environment. Activating Miniforge..." | log_with_service_name "Poetry" "$BLUE"
        source "$HOME/miniforge3/bin/activate"
        conda activate
    fi

    # Install Poetry if it's not already installed
    if ! command -v poetry >/dev/null 2>&1; then
        echo "Installing Poetry..." | log_with_service_name "Poetry" "$BLUE"
        curl -sSL https://install.python-poetry.org | python -
    else
        echo "Poetry is already installed." | log_with_service_name "Poetry" "$BLUE"
    fi

    os="$(uname)"
    if [ "$os" = "Darwin" ]; then
        export PATH="/Users/$(whoami)/.local/bin:$PATH"
    else
        export PATH="/home/$(whoami)/.local/bin:$PATH"
    fi

    # Configure Poetry to create virtual environments in the project directory
    poetry config virtualenvs.in-project true

    poetry lock

    # Install dependencies and create the virtual environment
    poetry install

    # Verify the presence of a .venv folder within the project directory
    if [ -d ".venv" ]; then
        echo ".venv folder is present in the project folder." | log_with_service_name "Poetry" "$BLUE"
    else
        echo "Poetry virtual environment setup failed." | log_with_service_name "Poetry" "$BLUE"
        exit 1
    fi
}


# Function to install Python 3.12 on Linux
install_python312() {
    echo "Checking for Python 3.12 installation..." | log_with_service_name "Python" $NC
    if python3.12 --version >/dev/null 2>&1; then
        echo "Python 3.12 is already installed." | log_with_service_name "Python" $NC
        return
    fi

    os="$(uname)"
    if [ "$os" = "Darwin" ]; then
        echo "Installing Python 3.12..." | log_with_service_name "Python" $NC
        brew install python@3.12
        python3.12 --version
    else
        echo "Installing Python 3.12..." | log_with_service_name "Python" $NC
        sudo add-apt-repository ppa:deadsnakes/ppa -y
        sudo apt update
        sudo apt install -y python3.12
        python3.12 --version
    fi
    echo "Python 3.12 is installed." | log_with_service_name "Python" $NC
}

# Function to start the Hub SurrealDB
start_hub_surrealdb() {
    PWD=$(pwd)
    echo "LOCAL_HUB: $LOCAL_HUB" | log_with_service_name "Config"
    if [ "$LOCAL_HUB" == "True" ]; then
        echo "Running Hub DB locally..." | log_with_service_name "HubDB" $RED
        
        INIT_PYTHON_PATH="$PWD/node/storage/hub/init_hub.py"
        chmod +x "$INIT_PYTHON_PATH"

        poetry run python "$INIT_PYTHON_PATH" 2>&1
        PYTHON_EXIT_STATUS=$?

        if [ $PYTHON_EXIT_STATUS -ne 0 ]; then
            echo "Hub DB initialization failed. Python script exited with status $PYTHON_EXIT_STATUS." | log_with_service_name "HubDB" $RED
            exit 1
        fi

        # Check if Hub DB is running
        if curl -s http://localhost:$HUB_DB_PORT/health > /dev/null; then
            echo "Hub DB is running successfully." | log_with_service_name "HubDB" $RED
        else
            echo "Hub DB failed to start. Please check the logs." | log_with_service_name "HubDB" $RED
            exit 1
        fi
    else
        echo "Not running Hub DB locally..." | log_with_service_name "HubDB" $RED
    fi

    poetry run python "$PWD/node/storage/hub/init_hub.py" --user 2>&1
    PYTHON_EXIT_STATUS=$?

    if [ $PYTHON_EXIT_STATUS -ne 0 ]; then
        echo "Hub DB sign in flow failed. Python script exited with status $PYTHON_EXIT_STATUS." | log_with_service_name "HubDB" $RED
        exit 1
    fi
}

start_local_surrealdb() {
    PWD=$(pwd)

    echo "Running Local DB..." | log_with_service_name "LocalDB" $RED
    
    INIT_PYTHON_PATH="$PWD/node/storage/db/init_db.py"
    chmod +x "$INIT_PYTHON_PATH"

    poetry run python "$INIT_PYTHON_PATH" 2>&1
    PYTHON_EXIT_STATUS=$?

    if [ $PYTHON_EXIT_STATUS -ne 0 ]; then
        echo "Local DB initialization failed. Python script exited with status $PYTHON_EXIT_STATUS." | log_with_service_name "LocalDB" $RED
        exit 1
    fi

    # Check if Local DB is running
    if curl -s http://localhost:$SURREALDB_PORT/health > /dev/null; then
        echo "Local DB is running successfully." | log_with_service_name "LocalDB" $RED
    else
        echo "Local DB failed to start. Please check the logs." | log_with_service_name "LocalDB" $RED
        exit 1
    fi
}

# Function to check and copy the .env file
check_and_copy_env() {
    if [ ! -f .env ]; then
        cp .env.example .env
        echo ".env file created from .env.example"
    else
        echo ".env file already exists."
    fi
}

# Function to check and set the private key
check_and_set_private_key() {
    os="$(uname)"
    if [[ -f .env ]]; then
        if [ "$os" = "Darwin" ]; then
            private_key_value=$(grep '^PRIVATE_KEY=' .env | awk -F'=' '{print $2}')
        else
            private_key_value=$(grep -oP '(?<=^PRIVATE_KEY=).*' .env)
        fi
        if [[ -n "$private_key_value" ]]; then
            echo "PRIVATE_KEY already set."
            return
        fi
    else
        touch .env
    fi

    read -p "No value for PRIVATE_KEY set. Would you like to generate one? (yes/no): " response
    if [[ "$response" == "yes" ]]; then
        private_key=$(poetry run python scripts/generate_user.py)

        # Remove existing PRIVATE_KEY line if it exists and add the new one without quotes
        if [ "$os" = "Darwin" ]; then
            sed -i '' "s/^PRIVATE_KEY=.*/PRIVATE_KEY=$private_key/" .env
        else
            sed -i "/^PRIVATE_KEY=/c\PRIVATE_KEY=$private_key" .env
        fi

        echo "Key pair generated and saved to .env file."
    else
        echo "Key pair generation aborted."
    fi
}

check_and_set_stability_key() {
    os="$(uname)"
    if [[ -f .env ]]; then
        if [ "$os" = "Darwin" ]; then
            stability_key_value=$(grep '^STABILITY_API_KEY=' .env | cut -d '=' -f2)
        else
            stability_key_value=$(grep -oP '(?<=^STABILITY_API_KEY=).*' .env)
        fi
        if [[ -n "$stability_key_value" ]]; then
            echo "STABILITY_API_KEY already set."
            return
        fi
    else
        touch .env
    fi

    read -p "No value for STABILITY_API_KEY set. You will need this to run the image agent examples. Would you like to enter a value for STABILITY_API_KEY? (yes/no): " response
    if [[ "$response" == "yes" ]]; then
        read -p "Enter the value for STABILITY_API_KEY: " stability_key

        # Ensure stability_key is not empty
        if [[ -z "$stability_key" ]]; then
            echo "No value entered for STABILITY_API_KEY."
            return
        fi

        # Remove existing STABILITY_API_KEY line if it exists and add the new one
        if [ "$os" = "Darwin" ]; then
            sed -i '' "s/^STABILITY_API_KEY=.*/STABILITY_API_KEY=\"$stability_key\"/" .env
        else
            sed -i "/^STABILITY_API_KEY=/c\STABILITY_API_KEY=\"$stability_key\"" .env
        fi

        echo "STABILITY_API_KEY has been updated in the .env file."
    else
        echo "STABILITY_API_KEY update aborted."
    fi
}


load_env_file() {
    CURRENT_DIR=$(pwd)
    ENV_FILE="$CURRENT_DIR/.env"
    
    # Debug: Check if .env file exists and permissions
    if [ -f "$ENV_FILE" ]; then
        echo ".env file found." | log_with_service_name "Config"
        # Load .env file
        set -a
        . "$ENV_FILE"
        set +a

        . .venv/bin/activate
    else
        echo ".env file does not exist in $CURRENT_DIR." | log_with_service_name "Config" 
        exit 1
    fi
}

load_config_constants() {
    CURRENT_DIR=$(pwd)
    CONFIG_FILE="$CURRENT_DIR/node/config.py"

    echo "Config file path: $CONFIG_FILE" | log_with_service_name "Config"

    if [ -f "$CONFIG_FILE" ]; then
        echo "config.py file found." | log_with_service_name "Config" 
        # Extract constants from config.py using Python
        eval "$(python3 -c "
import re
import ast

def parse_value(value):
    try:
        return ast.literal_eval(value)
    except:
        return value

with open('$CONFIG_FILE', 'r') as f:
    content = f.read()
constants = re.findall(r'^([A-Z_]+)\s*=\s*(.+)$', content, re.MULTILINE)
for name, value in constants:
    parsed_value = parse_value(value.strip())
    if isinstance(parsed_value, str):
        print(f'{name}=\"{parsed_value}\"')
    else:
        print(f'{name}={parsed_value}')
        ")"
    else
        echo "config.py file does not exist in $CURRENT_DIR/node/." | log_with_service_name "Config"
        exit 1
    fi

    echo "Config constants loaded successfully." | log_with_service_name "Config"
}

linux_start_servers() {
    # Echo start Servers
    echo "Starting Servers..." | log_with_service_name "Server" $BLUE

    # Get the config from the .env file
    server_type=${SERVER_TYPE:-"ws"} # Default to ws if not set
    num_servers=${NUM_SERVERS:-1} # Default to 1 if not set
    start_port=${NODE_PORT:-7002} # Starting port for alternate servers

    echo "Server type: $server_type" | log_with_service_name "Server" $BLUE
    echo "Number of additional servers: $num_servers" | log_with_service_name "Server" $BLUE
    echo "Additional servers start from port: $start_port" | log_with_service_name "Server" $BLUE

    # Define paths
    USER_NAME=$(whoami)
    CURRENT_DIR=$(pwd)
    PYTHON_APP_PATH="$CURRENT_DIR/.venv/bin/poetry"
    WORKING_DIR="$CURRENT_DIR/node"
    ENVIRONMENT_FILE_PATH="$CURRENT_DIR/.env"

    # First create HTTP server service (always port 7001)
    HTTP_SERVICE_FILE="nodeapp_http.service"
    echo "Starting HTTP server on port 7001..." | log_with_service_name "Server" $BLUE

    # Create the systemd service file for HTTP server
    cat <<EOF > /tmp/$HTTP_SERVICE_FILE
[Unit]
Description=Node HTTP Server
After=network.target

[Service]
ExecStart=$PYTHON_APP_PATH run python server/server.py --server-type http --port 7001
WorkingDirectory=$WORKING_DIR
EnvironmentFile=$ENVIRONMENT_FILE_PATH
User=$USER_NAME
Restart=always
TimeoutStopSec=90
KillMode=mixed
KillSignal=SIGTERM
SendSIGKILL=yes

# Environment variables for shutdown behavior
Environment=UVICORN_TIMEOUT=30
Environment=UVICORN_GRACEFUL_SHUTDOWN=30

[Install]
WantedBy=multi-user.target
EOF

    # Move the HTTP service file and start it
    sudo mv /tmp/$HTTP_SERVICE_FILE /etc/systemd/system/
    sudo systemctl daemon-reload
    if sudo systemctl enable $HTTP_SERVICE_FILE && sudo systemctl start $HTTP_SERVICE_FILE; then
        echo "HTTP server service started successfully on port 7001." | log_with_service_name "Server" $BLUE
    else
        echo "Failed to start HTTP server service." | log_with_service_name "Server" $RED
        return 1
    fi

    # Track all ports for .env file
    ports="7001"

    # Create services for additional servers
    for ((i=0; i<num_servers; i++)); do
        current_port=$((start_port + i))
        SERVICE_FILE="nodeapp_${server_type}_${current_port}.service"
        ports="${ports},${current_port}"

        echo "Starting $server_type server on port $current_port..." | log_with_service_name "Server" $BLUE

        # Create the systemd service file
        cat <<EOF > /tmp/$SERVICE_FILE
[Unit]
Description=Node $server_type Server on port $current_port
After=network.target nodeapp_http.service

[Service]
ExecStart=$PYTHON_APP_PATH run python server/server.py --server-type $server_type --port $current_port
WorkingDirectory=$WORKING_DIR
EnvironmentFile=$ENVIRONMENT_FILE_PATH
User=$USER_NAME
Restart=always
TimeoutStopSec=3
KillMode=mixed
KillSignal=SIGTERM
SendSIGKILL=yes

[Install]
WantedBy=multi-user.target
EOF

        # Move the service file and start it
        sudo mv /tmp/$SERVICE_FILE /etc/systemd/system/
        sudo systemctl daemon-reload
        if sudo systemctl enable $SERVICE_FILE && sudo systemctl start $SERVICE_FILE; then
            echo "$server_type server service started successfully on port $current_port." | log_with_service_name "Server" $BLUE
        else
            echo "Failed to start $server_type server service on port $current_port." | log_with_service_name "Server" $RED
        fi
    done

    # Update NODE_PORTS in .env file
    sed -i '/^NODE_PORTS=/d' $ENVIRONMENT_FILE_PATH
    echo "NODE_PORTS=$ports" >> $ENVIRONMENT_FILE_PATH
    echo "Updated NODE_PORTS in .env: $ports" | log_with_service_name "Server" $BLUE
}

darwin_start_servers() {
    # Echo start Node
    echo "Starting Servers..." | log_with_service_name "Server" $BLUE

    # Get the config from the .env file
    server_type=${SERVER_TYPE:-"ws"} # Default to ws if not set
    num_servers=${NUM_SERVERS:-1} # Default to 1 if not set
    start_port=${NODE_PORT:-7002} # Starting port for alternate servers

    echo "Server type: $server_type" | log_with_service_name "Server" $BLUE
    echo "Number of additional servers: $num_servers" | log_with_service_name "Server" $BLUE
    echo "Additional servers start from port: $start_port" | log_with_service_name "Server" $BLUE

    # Define paths
    USER_NAME=$(whoami)
    CURRENT_DIR=$(pwd)
    PYTHON_APP_PATH="$CURRENT_DIR/.venv/bin/poetry"
    WORKING_DIR="$CURRENT_DIR/node"
    ENVIRONMENT_FILE_PATH="$CURRENT_DIR/.env"
    SURRREALDB_PATH="/usr/local/bin"

    # First create HTTP server plist (always port 7001)
    HTTP_PLIST_FILE="com.example.nodeapp.http.plist"
    echo "Starting HTTP server on port 7001..." | log_with_service_name "Server" $BLUE

    PLIST_PATH=~/Library/LaunchAgents/$HTTP_PLIST_FILE

    # Create the launchd plist file for HTTP server
    cat <<EOF > ~/Library/LaunchAgents/$HTTP_PLIST_FILE
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.example.nodeapp.http</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_APP_PATH</string>
        <string>run</string>
        <string>python</string>
        <string>server/server.py</string>
        <string>--server-type</string>
        <string>http</string>
        <string>--port</string>
        <string>7001</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$WORKING_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ENVIRONMENT_FILE_PATH</key>
        <string>$ENVIRONMENT_FILE_PATH</string>
        <key>PATH</key>
        <string>$SURRREALDB_PATH:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/nodeapp_http.out</string>
    <key>StandardErrorPath</key>
    <string>/tmp/nodeapp_http.err</string>
</dict>
</plist>
EOF

    # Load and start HTTP server with error checking
    echo "Loading HTTP server service..." | log_with_service_name "Server" $BLUE
    if ! launchctl load $PLIST_PATH; then
        echo "Failed to load HTTP server service. Checking permissions..." | log_with_service_name "Server" $RED
        ls -l $PLIST_PATH
        exit 1
    fi

    # Verify service is running
    sleep 2
    if launchctl list | grep -q "com.example.nodeapp.http"; then
        echo "HTTP server service loaded successfully." | log_with_service_name "Server" $GREEN
    else
        echo "HTTP server service failed to load. Check system logs:" | log_with_service_name "Server" $RED
        sudo log show --predicate 'processImagePath contains "nodeapp"' --last 5m
        exit 1
    fi

    # Track all ports for .env file
    ports="7001"

    # Create plists for additional servers
    for ((i=0; i<num_servers; i++)); do
        current_port=$((start_port + i))
        PLIST_FILE="com.example.nodeapp.${server_type}_${current_port}.plist"
        PLIST_PATH=~/Library/LaunchAgents/$PLIST_FILE
        ports="${ports},${current_port}"

        echo "Starting $server_type server on port $current_port..." | log_with_service_name "Server" $BLUE

        cat <<EOF > ~/Library/LaunchAgents/$PLIST_FILE
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.example.nodeapp.${server_type}_${current_port}</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_APP_PATH</string>
        <string>run</string>
        <string>python</string>
        <string>server/server.py</string>
        <string>--server-type</string>
        <string>$server_type</string>
        <string>--port</string>
        <string>$current_port</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$WORKING_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ENVIRONMENT_FILE_PATH</key>
        <string>$ENVIRONMENT_FILE_PATH</string>
        <key>PATH</key>
        <string>$SURRREALDB_PATH:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/nodeapp_${server_type}_${current_port}.out</string>
    <key>StandardErrorPath</key>
    <string>/tmp/nodeapp_${server_type}_${current_port}.err</string>
</dict>
</plist>
EOF

        # Load with error checking
        echo "Loading $server_type server service on port $current_port..." | log_with_service_name "Server" $BLUE
        if ! launchctl load $PLIST_PATH; then
            echo "Failed to load $server_type server service. Checking permissions..." | log_with_service_name "Server" $RED
            ls -l $PLIST_PATH
            exit 1
        fi

        # Verify service is running
        sleep 2
        if launchctl list | grep -q "com.example.nodeapp.${server_type}_${current_port}"; then
            echo "$server_type server service loaded successfully on port $current_port." | log_with_service_name "Server" $GREEN
        else
            echo "$server_type server service failed to load on port $current_port." | log_with_service_name "Server" $RED
            exit 1
        fi
    done

    # Update NODE_PORTS in .env file (using sed compatible with macOS)
    sed -i '' '/^NODE_PORTS=/d' $ENVIRONMENT_FILE_PATH
    echo "NODE_PORTS=$ports" >> $ENVIRONMENT_FILE_PATH
    echo "Updated NODE_PORTS in .env: $ports" | log_with_service_name "Server" $BLUE
}

# Function to start the Celery worker
linux_start_celery_worker() {
    echo "Starting Celery worker..." | log_with_service_name "Celery" $GREEN
    
    # Prepare fields for the service file
    USER_NAME=$(whoami)
    CURRENT_DIR=$(pwd)
    WORKING_DIR="$CURRENT_DIR"
    ENVIRONMENT_FILE_PATH="$CURRENT_DIR/.env"

    # Create celery_worker_start.sh
    echo "#!/bin/bash" > celery_worker_start.sh
    echo "source $CURRENT_DIR/.venv/bin/activate" >> celery_worker_start.sh
    echo "exec celery -A node.worker.main.app worker --loglevel=info" >> celery_worker_start.sh
    chmod +x celery_worker_start.sh

    # Create temporary systemd service file
    cat > /tmp/celeryworker.service << EOF
[Unit]
Description=Celery Worker Service
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$WORKING_DIR
EnvironmentFile=$ENVIRONMENT_FILE_PATH
ExecStart=$CURRENT_DIR/celery_worker_start.sh
Restart=always

[Install]
WantedBy=multi-user.target
EOF

    # Move the temporary service file to systemd directory
    sudo cp /tmp/celeryworker.service /etc/systemd/system/celeryworker.service
    rm /tmp/celeryworker.service

    # Reload systemd to recognize new service
    sudo systemctl daemon-reload

    # Enable and start the Celery worker service
    sudo systemctl enable celeryworker
    sudo systemctl start celeryworker

    # Check until the Celery worker is up and running by checking the logs
    echo "Waiting for Celery worker to start..." | log_with_service_name "Celery" $GREEN
    while ! sudo journalctl -u celeryworker.service -n 100 | grep -q "celery@$(hostname) ready"; do
        sleep 1
    done

    sudo systemctl status celeryworker | log_with_service_name "Celery" $GREEN
}

darwin_start_celery_worker() {
    echo "Starting Celery worker..." | log_with_service_name "Celery" $GREEN
    
    # Prepare fields for the service file
    USER_NAME=$(whoami)
    CURRENT_DIR=$(pwd)
    WORKING_DIR="$CURRENT_DIR"
    ENVIRONMENT_FILE_PATH="$CURRENT_DIR/.env"
    EXECUTION_PATH="$CURRENT_DIR/celery_worker_start.sh"

    # Write celery_worker_start.sh with correct venv path
    cat <<EOF > celery_worker_start.sh
#!/bin/bash

# Exit on error
set -e

# Log function
log_error() {
    echo "\$(date '+%Y-%m-%d %H:%M:%S') ERROR: \$1" >> /tmp/celeryworker.err
}

# Check if virtual environment exists
if [ ! -f "$CURRENT_DIR/.venv/bin/activate" ]; then
    log_error "Virtual environment not found at $CURRENT_DIR/.venv/bin/activate"
    exit 1
fi

# Activate virtual environment
source "$CURRENT_DIR/.venv/bin/activate"

# Set file descriptor limits
ulimit -n 65536 || log_error "Failed to set ulimit"

# Start Celery
exec celery -A node.worker.main.app worker \
    --loglevel=info \
    --concurrency=120 \
    --max-tasks-per-child=100 \
    --max-memory-per-child=350000
EOF

    chmod +x celery_worker_start.sh

    # Create the launchd plist
    cat <<EOF > ~/Library/LaunchAgents/com.example.celeryworker.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.example.celeryworker</string>
    <key>ProgramArguments</key>
    <array>
        <string>$EXECUTION_PATH</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$WORKING_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ENVIRONMENT_FILE_PATH</key>
        <string>$ENVIRONMENT_FILE_PATH</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>SoftResourceLimits</key>
    <dict>
        <key>NumberOfFiles</key>
        <integer>65536</integer>
    </dict>
    <key>HardResourceLimits</key>
    <dict>
        <key>NumberOfFiles</key>
        <integer>65536</integer>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/celeryworker.out</string>
    <key>StandardErrorPath</key>
    <string>/tmp/celeryworker.err</string>
</dict>
</plist>
EOF

    # Unload if exists
    launchctl unload ~/Library/LaunchAgents/com.example.celeryworker.plist 2>/dev/null || true
    
    # Load and start
    if launchctl load ~/Library/LaunchAgents/com.example.celeryworker.plist; then
        echo "Celery worker service started successfully." | log_with_service_name "Celery" $GREEN
        return 0
    else
        echo "Failed to start Celery worker service." | log_with_service_name "Celery" $RED
        return 1
    fi
}

linux_setup_local_db() {
    echo "Starting PostgreSQL setup..." | log_with_service_name "PostgreSQL" $BLUE

    POSTGRES_BIN_PATH="/usr/lib/postgresql/16/bin"
    PSQL_BIN="$POSTGRES_BIN_PATH/psql"
    POSTGRESQL_CONF="/etc/postgresql/16/main/postgresql.conf"
    PG_HBA_CONF="/etc/postgresql/16/main/pg_hba.conf"

    # Check if PostgreSQL 16 is installed
    if command -v $PSQL_BIN &> /dev/null; then
        echo "PostgreSQL 16 is already installed." | log_with_service_name "PostgreSQL" $BLUE
    else
        echo "Installing PostgreSQL 16..." | log_with_service_name "PostgreSQL" $BLUE
        
        # Add PostgreSQL 16 repository
        sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
        wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
        
        # Update package lists
        sudo apt-get update
        
        # Install PostgreSQL 16
        sudo apt-get install -y postgresql-16 postgresql-contrib-16
        
        echo "PostgreSQL 16 installed successfully." | log_with_service_name "PostgreSQL" $BLUE
    fi

    echo "Configuring PostgreSQL..." | log_with_service_name "PostgreSQL" $BLUE
    
    sudo cp $POSTGRESQL_CONF ${POSTGRESQL_CONF}.bak
    
    echo "Setting port to $LOCAL_DB_PORT" | log_with_service_name "PostgreSQL" $BLUE
    sudo sed -i "s/^\s*#*\s*port\s*=.*/port = $LOCAL_DB_PORT/" $POSTGRESQL_CONF
    
    echo "Setting listen_addresses to '*'" | log_with_service_name "PostgreSQL" $BLUE
    sudo sed -i "s/^\s*#*\s*listen_addresses\s*=.*/listen_addresses = '*'/" $POSTGRESQL_CONF
    
    echo "Updating pg_hba.conf" | log_with_service_name "PostgreSQL" $BLUE
    if ! sudo grep -q "0.0.0.0/0" $PG_HBA_CONF; then
        echo "host    all             all             0.0.0.0/0               md5" | sudo tee -a $PG_HBA_CONF > /dev/null
    fi

    sudo sed -i "s/^local\s\+all\s\+all\s\+\(peer\|ident\)/local   all             all                                     md5/" $PG_HBA_CONF

    echo "PostgreSQL configured to listen on port $LOCAL_DB_PORT" | log_with_service_name "PostgreSQL" $BLUE

    echo "Restarting PostgreSQL service..." | log_with_service_name "PostgreSQL" $BLUE
    sudo systemctl restart postgresql
    sleep 5

    echo "Verifying PostgreSQL is running..." | log_with_service_name "PostgreSQL" $BLUE
    if sudo -u postgres $PSQL_BIN -p $LOCAL_DB_PORT -c "SELECT 1" >/dev/null 2>&1; then
        echo "PostgreSQL service started successfully on port $LOCAL_DB_PORT." | log_with_service_name "PostgreSQL" $BLUE
    else
        echo "Failed to connect to PostgreSQL on port $LOCAL_DB_PORT." | log_with_service_name "PostgreSQL" $BLUE
        exit 1
    fi

    echo "Creating database and user..." | log_with_service_name "PostgreSQL" $BLUE
    
    # Create user
    sudo -u postgres $PSQL_BIN -p $LOCAL_DB_PORT <<EOF
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$LOCAL_DB_USER') THEN
            CREATE USER $LOCAL_DB_USER WITH ENCRYPTED PASSWORD '$LOCAL_DB_PASSWORD';
        END IF;
    END
    \$\$;
EOF

    # Create database
    sudo -u postgres $PSQL_BIN -p $LOCAL_DB_PORT -c "CREATE DATABASE $LOCAL_DB_NAME WITH OWNER $LOCAL_DB_USER;"

    # Set permissions
    sudo -u postgres $PSQL_BIN -p $LOCAL_DB_PORT -d $LOCAL_DB_NAME <<EOF
    GRANT ALL PRIVILEGES ON DATABASE $LOCAL_DB_NAME TO $LOCAL_DB_USER;
    GRANT ALL ON SCHEMA public TO $LOCAL_DB_USER;
    ALTER SCHEMA public OWNER TO $LOCAL_DB_USER;
    GRANT ALL ON ALL TABLES IN SCHEMA public TO $LOCAL_DB_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $LOCAL_DB_USER;
EOF
    
    echo "Database and user setup completed successfully" | log_with_service_name "PostgreSQL" $BLUE
}

linux_start_local_db() {
    PWD=$(pwd)
    POSTGRES_BIN_PATH="/usr/lib/postgresql/16/bin"
    PSQL_BIN="$POSTGRES_BIN_PATH/psql"

    echo "Running Local DB..." | log_with_service_name "LocalDB" $RED
    
    INIT_PYTHON_PATH="$PWD/node/storage/db/init_db.py"
    chmod +x "$INIT_PYTHON_PATH"

    echo "Running init_db.py script..." | log_with_service_name "LocalDB" $RED
    poetry run python "$INIT_PYTHON_PATH" 2>&1
    PYTHON_EXIT_STATUS=$?

    if [ $PYTHON_EXIT_STATUS -ne 0 ]; then
        echo "Local DB initialization failed. Python script exited with status $PYTHON_EXIT_STATUS." | log_with_service_name "LocalDB" $RED
        exit 1
    fi

    echo "Checking if PostgreSQL is running..." | log_with_service_name "LocalDB" $RED
    if sudo -u postgres $PSQL_BIN -p $LOCAL_DB_PORT -c "SELECT 1" >/dev/null 2>&1; then
        echo "Local DB (PostgreSQL) is running successfully." | log_with_service_name "LocalDB" $RED
    else
        echo "Local DB (PostgreSQL) failed to start. Please check the logs." | log_with_service_name "LocalDB" $RED
        exit 1
    fi
}

darwin_setup_local_db() {
    echo "Starting PostgreSQL 16 setup..." | log_with_service_name "PostgreSQL" $BLUE

    # Check if PostgreSQL 16 is installed
    if brew list postgresql@16 &>/dev/null; then
        echo "PostgreSQL 16 is already installed." | log_with_service_name "PostgreSQL" $BLUE
    else
        echo "Installing PostgreSQL 16..." | log_with_service_name "PostgreSQL" $BLUE
        brew install postgresql@16
        echo "PostgreSQL 16 installed successfully." | log_with_service_name "PostgreSQL" $BLUE
    fi

    # Ensure PostgreSQL 16 is linked and in PATH
    if ! command -v psql &>/dev/null; then
        echo "Adding PostgreSQL 16 to PATH..." | log_with_service_name "PostgreSQL" $BLUE
        brew link --force postgresql@16
        echo 'export PATH="/usr/local/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc
        source ~/.zshrc
        echo "PostgreSQL 16 added to PATH." | log_with_service_name "PostgreSQL" $BLUE
    fi

    # Add PostgreSQL 16 to PATH for this session
    export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"

    echo "Configuring PostgreSQL 16..." | log_with_service_name "PostgreSQL" $BLUE
    
    POSTGRESQL_CONF="/opt/homebrew/var/postgresql@16/postgresql.conf"
    PG_HBA_CONF="/opt/homebrew/var/postgresql@16/pg_hba.conf"
    
    # Backup original configuration files
    cp $POSTGRESQL_CONF ${POSTGRESQL_CONF}.bak
    cp $PG_HBA_CONF ${PG_HBA_CONF}.bak
    
    echo "Setting port to $LOCAL_DB_PORT" | log_with_service_name "PostgreSQL" $BLUE
    sed -i '' "s/^#port = .*/port = $LOCAL_DB_PORT/" $POSTGRESQL_CONF
    
    echo "Setting listen_addresses to '*'" | log_with_service_name "PostgreSQL" $BLUE
    sed -i '' "s/^#listen_addresses = .*/listen_addresses = '*'/" $POSTGRESQL_CONF

    echo "Setting max_connections to 2000" | log_with_service_name "PostgreSQL" $BLUE
    sed -i '' "s/^#max_connections = .*/max_connections = 2000/" $POSTGRESQL_CONF
    
    echo "Updating pg_hba.conf" | log_with_service_name "PostgreSQL" $BLUE
    echo "host    all             all             0.0.0.0/0               md5" >> $PG_HBA_CONF

    echo "PostgreSQL 16 configured to listen on port $LOCAL_DB_PORT" | log_with_service_name "PostgreSQL" $BLUE

    echo "Stopping PostgreSQL 16 service..." | log_with_service_name "PostgreSQL" $BLUE
    brew services stop postgresql@16
    sleep 5

    echo "Starting PostgreSQL 16 service..." | log_with_service_name "PostgreSQL" $BLUE
    brew services start postgresql@16
    sleep 10  # Increased sleep time to allow PostgreSQL to fully start

    echo "Verifying PostgreSQL 16 is running..." | log_with_service_name "PostgreSQL" $BLUE
    max_attempts=5
    attempt=1
    while [ $attempt -le $max_attempts ]; do
        if pg_isready -p $LOCAL_DB_PORT; then
            echo "PostgreSQL 16 service is ready on port $LOCAL_DB_PORT." | log_with_service_name "PostgreSQL" $BLUE
            if psql -p $LOCAL_DB_PORT -c "SELECT 1" postgres >/dev/null 2>&1; then
                echo "Successfully connected to PostgreSQL 16 on port $LOCAL_DB_PORT." | log_with_service_name "PostgreSQL" $BLUE
                break
            else
                echo "pg_isready successful, but psql connection failed. Checking logs..." | log_with_service_name "PostgreSQL" $BLUE
                tail -n 50 /opt/homebrew/var/log/postgresql@16.log
            fi
        else
            echo "Attempt $attempt: PostgreSQL 16 is not ready on port $LOCAL_DB_PORT. Retrying..." | log_with_service_name "PostgreSQL" $BLUE
            sleep 5
            attempt=$((attempt+1))
        fi
    done

    if [ $attempt -gt $max_attempts ]; then
        echo "Failed to connect to PostgreSQL 16 after $max_attempts attempts. Checking logs..." | log_with_service_name "PostgreSQL" $RED
        tail -n 50 /opt/homebrew/var/log/postgresql@16.log
        echo "Current PostgreSQL processes:" | log_with_service_name "PostgreSQL" $RED
        ps aux | grep postgres
        echo "Current PostgreSQL configuration:" | log_with_service_name "PostgreSQL" $RED
        grep "port\|listen_addresses" $POSTGRESQL_CONF
        exit 1
    fi

    echo "Creating database and user..." | log_with_service_name "PostgreSQL" $BLUE
    
    # Create user
    psql -p $LOCAL_DB_PORT postgres <<EOF
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$LOCAL_DB_USER') THEN
            CREATE USER $LOCAL_DB_USER WITH ENCRYPTED PASSWORD '$LOCAL_DB_PASSWORD';
        END IF;
    END
    \$\$;
EOF

    # Create database
    psql -p $LOCAL_DB_PORT postgres -c "CREATE DATABASE $LOCAL_DB_NAME WITH OWNER $LOCAL_DB_USER;"

    # Set permissions
    psql -p $LOCAL_DB_PORT -d $LOCAL_DB_NAME <<EOF
    GRANT ALL PRIVILEGES ON DATABASE $LOCAL_DB_NAME TO $LOCAL_DB_USER;
    GRANT ALL ON SCHEMA public TO $LOCAL_DB_USER;
    ALTER SCHEMA public OWNER TO $LOCAL_DB_USER;
    GRANT ALL ON ALL TABLES IN SCHEMA public TO $LOCAL_DB_USER;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $LOCAL_DB_USER;
EOF
    
    echo "Database and user setup completed successfully" | log_with_service_name "PostgreSQL" $BLUE
}

darwin_start_local_db() {
    PWD=$(pwd)

    echo "Running Local DB..." | log_with_service_name "LocalDB" $RED
    
    INIT_PYTHON_PATH="$PWD/node/storage/db/init_db.py"
    chmod +x "$INIT_PYTHON_PATH"

    echo "Running init_db.py script..." | log_with_service_name "LocalDB" $RED
    poetry run python "$INIT_PYTHON_PATH" 2>&1
    PYTHON_EXIT_STATUS=$?

    if [ $PYTHON_EXIT_STATUS -ne 0 ]; then
        echo "Local DB initialization failed. Python script exited with status $PYTHON_EXIT_STATUS." | log_with_service_name "LocalDB" $RED
        exit 1
    fi

    echo "Checking if PostgreSQL 16 is running..." | log_with_service_name "LocalDB" $RED
    if psql -p $LOCAL_DB_PORT -c "SELECT 1" postgres >/dev/null 2>&1; then
        echo "Local DB (PostgreSQL 16) is running successfully." | log_with_service_name "LocalDB" $RED
    else
        echo "Local DB (PostgreSQL 16) failed to start. Please check the logs." | log_with_service_name "LocalDB" $RED
        exit 1
    fi
}

startup_summary() {
    echo "🔍 Checking status of all services..." | log_with_service_name "Summary" $BLUE
    
    # Use simple arrays with consistent indexing instead of associative arrays
    services=()
    statuses=()
    logs=()
    
    # Check PostgreSQL
    services+=("PostgreSQL")
    if [ "$os" = "Darwin" ]; then
        if psql -p $LOCAL_DB_PORT -c "SELECT 1" postgres >/dev/null 2>&1; then
            statuses+=("✅")
            logs+=("")
        else
            statuses+=("❌")
            logs+=("$(tail -n 20 /opt/homebrew/var/log/postgresql@16.log)")
        fi
    else
        if sudo -u postgres psql -p $LOCAL_DB_PORT -c "SELECT 1" >/dev/null 2>&1; then
            statuses+=("✅")
            logs+=("")
        else
            statuses+=("❌")
            logs+=("$(sudo journalctl -u postgresql -n 20)")
        fi
    fi

    # Check Local Hub if enabled
    if [ "$LOCAL_HUB" == "True" ]; then
        services+=("Hub_DB")
        if curl -s http://localhost:$HUB_DB_PORT/health > /dev/null; then
            statuses+=("✅")
            logs+=("")
        else
            statuses+=("❌")
            logs+=("$(tail -n 20 /tmp/hub_db.log 2>/dev/null || echo 'Log file not found')")
        fi
    fi

    # Check Celery
    services+=("Celery")
    if [ "$os" = "Darwin" ]; then
        if pgrep -f "celery.*worker" > /dev/null; then
            statuses+=("✅")
            logs+=("")
        else
            statuses+=("❌")
            logs+=("$(tail -n 20 /tmp/celeryworker.out 2>/dev/null || echo 'Log file not found')")
        fi
    else
        if systemctl is-active --quiet celeryworker; then
            statuses+=("✅")
            logs+=("")
        else
            statuses+=("❌")
            logs+=("$(sudo journalctl -u celeryworker -n 20)")
        fi
    fi

    # Wait before checking HTTP and WS servers
    echo "Waiting for HTTP and WebSocket servers to fully initialize..." | log_with_service_name "Summary" $BLUE
    sleep 5

    # Check Node HTTP Server
    services+=("HTTP_Server")
    if [ "$os" = "Darwin" ]; then
        if curl -s http://localhost:7001/health > /dev/null; then
            statuses+=("✅")
            logs+=("")
        else
            statuses+=("❌")
            logs+=("$(tail -n 20 /tmp/nodeapp_http.out 2>/dev/null || echo 'Log file not found')")
        fi
    else
        if curl -s http://localhost:7001/health > /dev/null; then
            statuses+=("✅")
            logs+=("")
        else
            statuses+=("❌")
            logs+=("$(sudo journalctl -u nodeapp_http -n 20)")
        fi
    fi

    # Check Secondary Servers (WS or gRPC)
    for port in $(echo $NODE_PORTS | tr ',' ' '); do
        if [ "$port" != "7001" ]; then  # Skip HTTP port
            services+=("$(echo $SERVER_TYPE | tr '[:lower:]' '[:upper:]')_Server_${port}")
            
            # Health check based on server type
            if [ "${SERVER_TYPE}" = "ws" ]; then
                # WebSocket health check using /health endpoint
                if curl -s http://localhost:$port/health > /dev/null; then
                    statuses+=("✅")
                    logs+=("")
                else
                    if [ "$os" = "Darwin" ]; then
                        logs+=("$(tail -n 20 /tmp/nodeapp_ws_$port.out 2>/dev/null || echo 'Log file not found')")
                    else
                        logs+=("$(sudo journalctl -u nodeapp_ws_$port -n 20)")
                    fi
                    statuses+=("❌")
                fi
            else  # grpc
                # gRPC health check using is_alive
                if python3 -c "
import grpc
import sys
from node.server import grpc_server_pb2_grpc, grpc_server_pb2
from google.protobuf.empty_pb2 import Empty
channel = grpc.insecure_channel('localhost:$port')
stub = grpc_server_pb2_grpc.GrpcServerStub(channel)
try:
    response = stub.is_alive(Empty())
    sys.exit(0 if response.ok else 1)
except Exception as e:
    sys.exit(1)
" > /dev/null 2>&1; then
                    statuses+=("✅")
                    logs+=("")
                else
                    if [ "$os" = "Darwin" ]; then
                        logs+=("$(tail -n 20 /tmp/nodeapp_grpc_$port.out 2>/dev/null || echo 'Log file not found')")
                    else
                        logs+=("$(sudo journalctl -u nodeapp_grpc_$port -n 20)")
                    fi
                    statuses+=("❌")
                fi
            fi
        fi
    done

    # Print formatted summary
    echo -e "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | log_with_service_name "Summary" $BLUE
    echo -e "           🔍 SERVICE STATUS              " | log_with_service_name "Summary" $BLUE
    echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | log_with_service_name "Summary" $BLUE
    echo -e "                                         " | log_with_service_name "Summary" $BLUE

    # Print status for each service
    local failed_services=0
    for i in "${!services[@]}"; do
        service_name="${services[$i]}"
        service_name="${service_name//_/ }"  # Replace underscores with spaces
        printf "  %-20s %s\n" "$service_name" "${statuses[$i]}" | log_with_service_name "Summary" $BLUE
        if [ "${statuses[$i]}" == "❌" ]; then
            failed_services=$((failed_services + 1))
        fi
    done

    echo -e "                                         " | log_with_service_name "Summary" $BLUE
    echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" | log_with_service_name "Summary" $BLUE

    # Print logs for failed services
    if [ $failed_services -gt 0 ]; then
        echo -e "\n📋 Error Logs for Failed Services:" | log_with_service_name "Summary" $RED
        for i in "${!services[@]}"; do
            if [ "${statuses[$i]}" == "❌" ]; then
                service_name="${services[$i]}"
                service_name="${service_name//_/ }"
                echo -e "\n🔴 ${service_name} Logs:" | log_with_service_name "Summary" $RED
                echo "${logs[$i]}" | log_with_service_name "Summary" $RED
            fi
        done
        exit 1
    else
        echo -e "\n✨ All services started successfully!" | log_with_service_name "Summary" $GREEN
    fi
}   

print_logo(){
    printf """
                 █▀█                  
              ▄▄▄▀█▀            
              █▄█ █    █▀█        
           █▀█ █  █ ▄▄▄▀█▀      
        ▄▄▄▀█▀ █  █ █▄█ █ ▄▄▄       
        █▄█ █  █  █  █  █ █▄█        ███╗   ██╗ █████╗ ██████╗ ████████╗██╗  ██╗ █████╗ 
     ▄▄▄ █  █  █  █  █  █  █ ▄▄▄     ████╗  ██║██╔══██╗██╔══██╗╚══██╔══╝██║  ██║██╔══██╗
     █▄█ █  █  █  █▄█▀  █  █ █▄█     ██╔██╗ ██║███████║██████╔╝   ██║   ███████║███████║
      █  █   ▀█▀  █▀▀  ▄█  █  █      ██║╚██╗██║██╔══██║██╔═══╝    ██║   ██╔══██║██╔══██║
      █  ▀█▄  ▀█▄ █ ▄█▀▀ ▄█▀  █      ██║ ╚████║██║  ██║██║        ██║   ██║  ██║██║  ██║
       ▀█▄ ▀▀█  █ █ █ ▄██▀ ▄█▀       ╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝        ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝
         ▀█▄ █  █ █ █ █  ▄█▀                         Decentralized Multi-Agent Workflows
            ▀█  █ █ █ █ ▌▀                                                 \e]8;;https://www.naptha.ai\e\\www.naptha.ai\e]8;;\e\\
              ▀▀█ █ ██▀▀                                                          
    """
    echo -e "\n"
    printf "✨ ✨ ✨ Launching... While you wait, please star our repo \e]8;;https://github.com/NapthaAI/node\e\\https://github.com/NapthaAI/node\e]8;;\e\\ ✨ ✨ ✨"
    echo -e "\n"
}

main() {
    os="$(uname)"
    # Main execution flow
    if [ "$os" = "Darwin" ]; then
        print_logo
        install_python312
        install_surrealdb
        check_and_copy_env
        load_env_file
        load_config_constants
        darwin_install_ollama
        darwin_install_miniforge
        darwin_install_docker
        darwin_clean_node
        darwin_start_rabbitmq
        setup_poetry
        check_and_set_private_key
        check_and_set_stability_key
        start_hub_surrealdb
        darwin_setup_local_db
        darwin_start_local_db
        darwin_start_servers
        darwin_start_celery_worker
        startup_summary
    else
        print_logo
        install_python312
        install_surrealdb
        check_and_copy_env
        load_env_file
        load_config_constants
        linux_install_ollama
        linux_install_miniforge
        linux_install_docker
        linux_clean_node
        linux_start_rabbitmq
        setup_poetry
        check_and_set_private_key
        check_and_set_stability_key
        start_hub_surrealdb
        linux_setup_local_db
        linux_start_local_db
        linux_start_servers
        linux_start_celery_worker
        startup_summary
    fi

    echo "Setup complete. Applications are running." | log_with_service_name "System" $GREEN

}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi