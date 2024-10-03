#!/bin/bash

# Source the launch.sh script to import functions
source ./launch.sh

# Function to stop SurrealDB
stop_surrealdb() {
    # Run the export_hub.py script using the project's virtual environment
    echo "Exporting SurrealDB data..."
    PROJECT_ROOT=$(pwd)
    VENV_PATH="$PROJECT_ROOT/.venv"
    EXPORT_SCRIPT_PATH="$PROJECT_ROOT/node/storage/hub/export_hub.py"
    
    if [ -f "$VENV_PATH/bin/activate" ]; then
        source "$VENV_PATH/bin/activate"
        python "$EXPORT_SCRIPT_PATH"
        deactivate
    else
        echo "Virtual environment not found at $VENV_PATH"
    fi
    
    surrealdb_hub_pid=$(lsof -ti:3001)
    if [ ! -z "$surrealdb_hub_pid" ]; then
        echo "Stopping SurrealDB on port 3001"
        kill -9 $surrealdb_hub_pid
    else
        echo "No SurrealDB process found running on port 3001"
    fi

    surrealdb_db_pid=$(lsof -ti:3002)
    if [ ! -z "$surrealdb_db_pid" ]; then
        echo "Stopping SurrealDB on port 3002"
        kill -9 $surrealdb_db_pid
    else
        echo "No SurrealDB process found running on port 3002"
    fi
}

# Load the .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo ".env file not found. Using default values."
    NUM_SERVERS=1
fi

load_config_constants

os=$(uname)
if [ "$os" = "Darwin" ]; then
    # Stop the services
    launchctl unload ~/Library/LaunchAgents/com.example.celeryworker.plist
    for i in $(seq 0 $((${NUM_SERVERS:-1} - 1))); do
        echo "Unloading nodeapp_$i.plist"
        launchctl unload ~/Library/LaunchAgents/com.example.nodeapp_$i.plist
    done
    launchctl unload ~/Library/LaunchAgents/com.example.ollama.plist
    brew services stop rabbitmq

    # Remove the service files
    rm ~/Library/LaunchAgents/com.example.celeryworker.plist
    for i in $(seq 0 $((${NUM_SERVERS:-1} - 1))); do
        rm ~/Library/LaunchAgents/com.example.nodeapp_$i.plist
    done
    rm ~/Library/LaunchAgents/com.example.ollama.plist

    # Stop SurrealDB
    stop_surrealdb

    # Provide feedback
    echo "Services stopped and plist files removed."
else
    # Stop the services
    sudo systemctl stop celeryworker.service
    for i in $(seq 0 $((${NUM_SERVERS:-1} - 1))); do
        echo "Stopping nodeapp_$i.service"
        sudo systemctl stop nodeapp_$i.service
    done
    sudo systemctl stop ollama.service
    sudo systemctl stop rabbitmq-server.service

    # Disable the services
    sudo systemctl disable celeryworker.service
    for i in $(seq 0 $((${NUM_SERVERS:-1} - 1))); do
        echo "Disabling nodeapp_$i.service"
        sudo systemctl disable nodeapp_$i.service
    done
    sudo systemctl disable ollama.service
    sudo systemctl disable rabbitmq-server.service

    # Remove the service files
    sudo rm /etc/systemd/system/celeryworker.service
    for i in $(seq 0 $((${NUM_SERVERS:-1} - 1))); do
        echo "Removing nodeapp_$i.service"
        sudo rm /etc/systemd/system/nodeapp_$i.service
    done
    sudo rm /etc/systemd/system/ollama.service
    sudo rm /etc/systemd/system/rabbitmq-server.service

    # Stop SurrealDB
    stop_surrealdb

    echo "Services stopped and systemd files removed."
fi