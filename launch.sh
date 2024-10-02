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

    SURREALDB_INSTALL_PATH="/home/$(whoami)/.surrealdb"
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
        echo "Docker jobs are disabled." | log_with_service_name "Docker" $RED
        return
    fi

    if docker --version >/dev/null 2>&1; then
        echo "Docker is already installed." | log_with_service_name "Docker" $RED
    else
        echo "Installing Docker..." | log_with_service_name "Docker" $RED

        # Check if Homebrew is installed
        if ! command -v brew >/dev/null 2>&1; then
            echo "Homebrew not found. Installing Homebrew..." | log_with_service_name "Homebrew" $NC
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi

        # Install Docker using Homebrew
        brew install --cask docker

        echo "Docker installed." | log_with_service_name "Docker" $RED
        echo "Starting Docker..." | log_with_service_name "Docker" $RED

        # Start Docker.app
        open /Applications/Docker.app

        # Wait for Docker to start
        echo "Waiting for Docker to start..."
        while ! docker system info >/dev/null 2>&1; do
            sleep 1
        done
    fi

    echo "Checking if Docker is running..." | log_with_service_name "Docker" $RED
    if docker info >/dev/null 2>&1; then
        echo "Docker is already running." | log_with_service_name "Docker" $RED
    else
        echo "Failed to start Docker. Exiting..." | log_with_service_name "Docker" $RED
        exit 1
    fi

    echo "Docker is running." | log_with_service_name "Docker" $RED
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
    if [ "$LOCAL_HUB" == "true" ]; then
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

    # Get the port and number of servers from the .env file
    port=${NODE_PORT:-7001} # Default to 7001 if not set
    num_servers=${NUM_SERVERS:-1} # Default to 1 if not set
    echo "Port: $port" | log_with_service_name "Server" $BLUE
    echo "Number of servers: $num_servers" | log_with_service_name "Server" $BLUE

    # Define paths
    USER_NAME=$(whoami)
    CURRENT_DIR=$(pwd)
    PYTHON_APP_PATH="$CURRENT_DIR/.venv/bin/poetry"
    WORKING_DIR="$CURRENT_DIR/node"
    ENVIRONMENT_FILE_PATH="$CURRENT_DIR/.env"

    # Array to store server ports
    server_ports=()

    for ((i=0; i<num_servers; i++))
    do
        server_port=$((port + i))
        SERVICE_FILE="nodeapp_$i.service"
        server_ports+=($server_port)

        echo "Starting application server $i on port $server_port..." | log_with_service_name "Server" $BLUE

        # Create the systemd service file for nodeapp
        cat <<EOF > /tmp/$SERVICE_FILE
[Unit]
Description=Node Application Server $i
After=network.target

[Service]
ExecStart=$PYTHON_APP_PATH run python server/server.py --port $server_port
WorkingDirectory=$WORKING_DIR
EnvironmentFile=$ENVIRONMENT_FILE_PATH
User=$USER_NAME
Restart=always

[Install]
WantedBy=multi-user.target
EOF

        # Check if the service file was created successfully
        if [ ! -f /tmp/$SERVICE_FILE ]; then
            echo "Failed to create service file for server $i" | log_with_service_name "Server" $RED
            continue
        fi

        # Move the service file to the systemd directory
        sudo mv /tmp/$SERVICE_FILE /etc/systemd/system/

        # Reload systemd, enable and start the service
        sudo systemctl daemon-reload
        if sudo systemctl enable $SERVICE_FILE && sudo systemctl start $SERVICE_FILE; then
            echo "Node application $i service started successfully on port $server_port." | log_with_service_name "Server" $BLUE
        else
            echo "Failed to start Node application $i service on port $server_port." | log_with_service_name "Server" $RED
        fi
    done

    # Update NODE_PORTS in .env file
    node_ports_string=$(IFS=,; echo "${server_ports[*]}")
    sed -i '/^NODE_PORTS=/d' $ENVIRONMENT_FILE_PATH
    echo "NODE_PORTS=$node_ports_string" >> $ENVIRONMENT_FILE_PATH
    echo "Updated NODE_PORTS in .env: $node_ports_string" | log_with_service_name "Server" $BLUE
}

darwin_start_servers() {
    # Echo start Node
    echo "Starting Servers..." | log_with_service_name "Server" $BLUE

    # Get the port and number of servers from the .env file
    port=${NODE_PORT:-7001} # Default to 7001 if not set
    num_servers=${NUM_SERVERS:-1} # Default to 1 if not set
    echo "Port: $port" | log_with_service_name "Server" $BLUE
    echo "Number of servers: $num_servers" | log_with_service_name "Server" $BLUE

    # Define paths
    USER_NAME=$(whoami)
    CURRENT_DIR=$(pwd)
    PYTHON_APP_PATH="$CURRENT_DIR/.venv/bin/poetry"
    WORKING_DIR="$CURRENT_DIR/node"
    ENVIRONMENT_FILE_PATH="$CURRENT_DIR/.env"
    SURRREALDB_PATH="/usr/local/bin"

    for ((i=0; i<num_servers; i++))
    do
        server_port=$((port + i))
        PLIST_FILE="com.example.nodeapp_$i.plist"

        echo "Starting application server $i on port $server_port..." | log_with_service_name "Server" $BLUE

        # Create the launchd plist file for nodeapp
        cat <<EOF > ~/Library/LaunchAgents/$PLIST_FILE
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.example.nodeapp_$i</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_APP_PATH</string>
        <string>run</string>
        <string>python</string>
        <string>server/server.py</string>
        <string>--port</string>
        <string>$server_port</string>
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
    <string>/tmp/nodeapp_$i.out</string>
    <key>StandardErrorPath</key>
    <string>/tmp/nodeapp_$i.err</string>
</dict>
</plist>
EOF

        # Check if the plist file was created successfully
        if [ ! -f ~/Library/LaunchAgents/$PLIST_FILE ]; then
            echo "Failed to create plist file for server $i" | log_with_service_name "Server" $RED
            continue
        fi

        # Validate the plist file
        if ! plutil -lint ~/Library/LaunchAgents/$PLIST_FILE > /dev/null 2>&1; then
            echo "Invalid plist file for server $i" | log_with_service_name "Server" $RED
            continue
        fi

        # Load and start the nodeapp service
        if launchctl load ~/Library/LaunchAgents/$PLIST_FILE; then
            echo "Node application $i service started successfully on port $server_port." | log_with_service_name "Server" $BLUE
        else
            echo "Failed to start Node application $i service on port $server_port." | log_with_service_name "Server" $RED
        fi

    done
}

# Function to start the Celery worker
linux_start_celery_worker() {
    echo "Starting Celery worker..." | log_with_service_name "Celery" $GREEN
    
    # Prepare fields for the service file
    USER_NAME=$(whoami)
    CURRENT_DIR=$(pwd)
    WORKING_DIR="$CURRENT_DIR"
    ENVIRONMENT_FILE_PATH="$CURRENT_DIR/.env"
    EXECUTION_PATH="$CURRENT_DIR/celery_worker_start.sh"

    # cd to the directory of the service file
    cd ops/systemd

    # Replace the fieldsin the service file with the dynamic path
    sed -i "s|ExecStart=.*|ExecStart=$EXECUTION_PATH|" celeryworker.service
    sed -i "s|WorkingDirectory=.*|WorkingDirectory=$WORKING_DIR|" celeryworker.service
    sed -i "s|EnvironmentFile=.*|EnvironmentFile=$ENVIRONMENT_FILE_PATH|" celeryworker.service
    sed -i "/^User=/c\User=$USER_NAME" celeryworker.service

    # cd back to the original directory
    cd -

    # Write celery_worker_start.sh
    echo "#!/bin/bash" > celery_worker_start.sh
    echo "source $CURRENT_DIR/.venv/bin/activate" >> celery_worker_start.sh
    echo "exec celery -A node.worker.main.app worker --loglevel=info" >> celery_worker_start.sh

    # Make the script executable
    chmod +x celery_worker_start.sh

    # Move the celeryworker.service to the systemd directory
    sudo cp ops/systemd/celeryworker.service /etc/systemd/system/celeryworker.service

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

    # Check if the Celery worker service is running
    sudo systemctl status celeryworker | log_with_service_name "Celery" $GREEN

    # Change back to the original directory (if needed)
    cd -
}

darwin_start_celery_worker() {
    echo "Starting Celery worker..." | log_with_service_name "Celery" $GREEN
    
    # Prepare fields for the service file
    USER_NAME=$(whoami)
    CURRENT_DIR=$(pwd)
    WORKING_DIR="$CURRENT_DIR"
    ENVIRONMENT_FILE_PATH="$CURRENT_DIR/.env"
    EXECUTION_PATH="$CURRENT_DIR/celery_worker_start.sh"

    # Write celery_worker_start.sh
    echo "#!/bin/bash" > celery_worker_start.sh
    echo "source $CURRENT_DIR/.venv/bin/activate" >> celery_worker_start.sh
    echo "exec celery -A node.worker.main.app worker --loglevel=info" >> celery_worker_start.sh

    # Make the script executable
    chmod +x celery_worker_start.sh

    # Create the launchd plist file for Celery worker
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
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/celeryworker.out</string>
    <key>StandardErrorPath</key>
    <string>/tmp/celeryworker.err</string>
</dict>
</plist>
EOF

    # Load and start the celeryworker service
    launchctl load ~/Library/LaunchAgents/com.example.celeryworker.plist
    launchctl start com.example.celeryworker

    echo "Celery worker service started successfully." | log_with_service_name "Celery" $GREEN
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
        load_env_file
        load_config_constants
        darwin_install_ollama
        darwin_install_miniforge
        darwin_install_docker
        darwin_clean_node
        darwin_start_rabbitmq
        setup_poetry
        check_and_copy_env
        check_and_set_private_key
        check_and_set_stability_key
        start_hub_surrealdb
        start_local_surrealdb
        darwin_start_servers
        darwin_start_celery_worker
    else
        print_logo
        install_python312
        install_surrealdb
        load_env_file
        load_config_constants
        linux_install_ollama
        linux_install_miniforge
        linux_install_docker
        linux_clean_node
        linux_start_rabbitmq
        setup_poetry
        check_and_copy_env
        check_and_set_private_key
        check_and_set_stability_key
        start_hub_surrealdb
        start_local_surrealdb
        linux_start_servers
        linux_start_celery_worker
    fi

    echo "Setup complete. Applications are running." | log_with_service_name "System" $GREEN

    # Keep the script running to maintain background processes
    wait
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi