#!/bin/bash

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Function for prefixed logging
log_with_service_name() {
    local service_name=$1
    local color=$2
    while IFS= read -r line; do
        echo -e "${color}[$service_name]${NC} $line"
    done
}

# Function to install SurrealDB
install_surrealdb() {
    echo "Installing SurrealDB..." | log_with_service_name "SurrealDB" $GREEN

    SURREALDB_INSTALL_PATH="/Users/$(whoami)/.surrealdb"
    SURREALDB_BINARY="$SURREALDB_INSTALL_PATH/surreal"

    if [ -f /usr/local/bin/surreal ]; then
        echo "SurrealDB is already installed." | log_with_service_name "SurrealDB" $GREEN
        return
    fi

    echo "Installing SurrealDB..." | log_with_service_name "SurrealDB" $GREEN

    # Install SurrealDB
    curl -sSf https://install.surrealdb.com | bash

    if [ -f "$SURREALDB_BINARY" ]; then
        sudo mv "$SURREALDB_BINARY" /usr/local/bin/surreal
        echo "SurrealDB binary moved to /usr/local/bin."
    fi

    if [ ! -f /usr/local/bin/surreal ]; then
        echo "SurrealDB installation failed." | log_with_service_name "SurrealDB" $RED
        exit 1
    fi
}

# Function for manual installation of Ollama
install_ollama() {
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
    echo "Pulling ollama models." | log_with_service_name "Ollama" $RED
    ollama pull phi
}

install_miniforge() {
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

clean_node() {
    # Echo start cleaning
    echo "Cleaning node..." | log_with_service_name "Node" $NC

    # Remove node_modules if it exists
    if [ -d "node_modules" ]; then
        rm -rf node_modules
        echo "Removed node_modules directory." | log_with_service_name "Node" $NC
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
        echo "Running make pyproject-clean..." | log_with_service_name "Node" $NC
        make pyproject-clean
    else
        echo "Makefile not found. Skipping make pyproject-clean." | log_with_service_name "Node" $NC
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

install_docker() {
    echo "Checking for Docker installation..." | log_with_service_name "Docker" $RED

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


# Function to start RabbitMQ in Docker
start_rabbitmq() {
    # Echo start RabbitMQ
    echo "Starting RabbitMQ..." | log_with_service_name "RabbitMQ" $GREEN

    # Check if RabbitMQ container exists and is running
    if sudo docker ps --filter "name=rabbitmq" --filter "status=running" | grep -q rabbitmq; then
        echo "RabbitMQ is already running." | log_with_service_name "RabbitMQ" $GREEN
        return
    fi

    # Check if RabbitMQ container exists but stopped
    if sudo docker ps --all --filter "name=rabbitmq" | grep -q rabbitmq; then
        echo "RabbitMQ container exists but stopped. Starting it..." | log_with_service_name "RabbitMQ" $GREEN
        sudo docker start rabbitmq
    else
        echo "Starting RabbitMQ in Docker..." | log_with_service_name "RabbitMQ" $GREEN
        sudo docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
        sleep 10
        sudo docker start rabbitmq
    fi

    # Wait for RabbitMQ to start
    until sudo docker exec rabbitmq rabbitmqctl list_queues >/dev/null 2>&1; do
        echo "Waiting for RabbitMQ to start..." | log_with_service_name "RabbitMQ" $GREEN
        sleep 1
    done
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

    export PATH="/home/$(whoami)/.local/bin:$PATH"

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


install_python312() {
    echo "Checking for Python 3.12 installation..." | log_with_service_name "Python" $NC
    if python3.12 --version >/dev/null 2>&1; then
        echo "Python 3.12 is already installed." | log_with_service_name "Python" $NC
    else
        echo "Installing Python 3.12..." | log_with_service_name "Python" $NC
        brew install python@3.12
        python3.12 --version
    fi
    echo "Python 3.12 is installed." | log_with_service_name "Python" $NC
}

start_hub_surrealdb() {
    if [ "$LOCAL_HUB" = true ]; then
        echo "Running Hub DB locally..." | log_with_service_name "HubDB" $RED
        
        PWD=$(pwd)
        INIT_PYTHON_PATH="$PWD/node/storage/hub/init_hub.py"
        chmod +x "$INIT_PYTHON_PATH"

        poetry run python "$INIT_PYTHON_PATH"
    else
        echo "Not running Hub DB locally..." | log_with_service_name "HubDB" $RED
    fi
}

check_and_copy_env() {
    if [ ! -f .env ]; then
        cp .env.example .env
        echo ".env file created from .env.example"
    else
        echo ".env file already exists."
    fi
}

check_and_set_private_key() {
    # Check if .env file exists and if PRIVATE_KEY has a value
    if [[ -f .env ]]; then
        private_key_value=$(grep '^PRIVATE_KEY=' .env | awk -F'=' '{print $2}')
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

        # Remove existing PRIVATE_KEY line if it exists and add the new one
        if grep -q "^PRIVATE_KEY=" .env; then
            sed -i '' "s/^PRIVATE_KEY=.*/PRIVATE_KEY=\"$private_key\"/" .env
        else
            echo "PRIVATE_KEY=\"$private_key\"" >> .env
        fi

        echo "Key pair generated and saved to .env file."
    else
        echo "Key pair generation aborted."
    fi
}

check_and_set_stability_key() {
    # Check if .env file exists and if STABILITY_API_KEY has a value
    if [[ -f .env ]]; then
        stability_key_value=$(grep '^STABILITY_API_KEY=' .env | awk -F'=' '{print $2}')
        if [[ -n "$stability_key_value" ]]; then
            echo "STABILITY_API_KEY already set."
            return
        fi
    else
        touch .env
    fi
    
    read -p "No value for STABILITY_API_KEY set. You will need this to run the image module examples. Would you like to enter a value for STABILITY_API_KEY? (yes/no): " response
    if [[ "$response" == "yes" ]]; then
        read -p "Enter the value for STABILITY_API_KEY: " stability_key

        # Ensure stability_key is not empty
        if [[ -z "$stability_key" ]]; then
            echo "No value entered for STABILITY_API_KEY."
            return
        fi

        # Remove existing STABILITY_API_KEY line if it exists and add the new one
        if grep -q "^STABILITY_API_KEY=" .env; then
            sed -i '' "s/^STABILITY_API_KEY=.*/STABILITY_API_KEY=\"$stability_key\"/" .env
        else
            echo "STABILITY_API_KEY=\"$stability_key\"" >> .env
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
        echo ".env file found." | log_with_service_name "EnvLoader" "info"
        # Load .env file
        set -a
        . "$ENV_FILE"
        set +a

        . .venv/bin/activate
    else
        echo ".env file does not exist in $CURRENT_DIR." | log_with_service_name "EnvLoader" "error"
        exit 1
    fi
}

start_node() {
    # Echo start Node
    echo "Starting Node..." | log_with_service_name "Node" $BLUE

    # Get the port from the .env file
    port=${NODE_PORT:-3000} # Default to 3000 if not set
    echo "Port: $port"

    echo "Starting Node application..." | log_with_service_name "Node" "info"

    # Define paths
    USER_NAME=$(whoami)
    CURRENT_DIR=$(pwd)
    PYTHON_APP_PATH="$CURRENT_DIR/.venv/bin/poetry"
    WORKING_DIR="$CURRENT_DIR/node"
    ENVIRONMENT_FILE_PATH="$CURRENT_DIR/.env"
    PLIST_FILE="com.example.nodeapp.plist"
    SURRREALDB_PATH="/usr/local/bin"

    # Create the launchd plist file for nodeapp
    cat <<EOF > ~/Library/LaunchAgents/$PLIST_FILE
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.example.nodeapp</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_APP_PATH</string>
        <string>run</string>
        <string>python</string>
        <string>main.py</string>
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
    <string>/tmp/nodeapp.out</string>
    <key>StandardErrorPath</key>
    <string>/tmp/nodeapp.err</string>
</dict>
</plist>
EOF

    # Load and start the nodeapp service
    # launchctl unload ~/Library/LaunchAgents/$PLIST_FILE
    launchctl load ~/Library/LaunchAgents/$PLIST_FILE
    launchctl start com.example.nodeapp

    echo "Node application service started successfully." | log_with_service_name "Node" "info"
}

# Function to start the Celery worker
start_celery_worker() {
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

    echo "Celery worker service started successfully." | log_with_service_name "Celery" "info"
}

# Main execution flow
install_python312
install_surrealdb
# install_ollama
install_miniforge
clean_node
install_docker
start_rabbitmq
setup_poetry
check_and_copy_env
check_and_set_private_key
check_and_set_stability_key
load_env_file
start_hub_surrealdb
start_node
start_celery_worker

echo "Setup complete. Applications are running." | log_with_service_name "System" $GREEN

# Keep the script running to maintain background processes
wait
