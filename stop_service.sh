#!/bin/bash

# Source the launch.sh script to import functions
source ./launch.sh

# Function to stop SurrealDB
stop_surrealdb() {
    # Find and kill the SurrealDB process running on port 3001
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
server_type=${SERVER_TYPE:-"ws"}
start_port=${NODE_PORT:-7002} 

os=$(uname)
if [ "$os" = "Darwin" ]; then
    # Define LaunchAgents path
    LAUNCH_AGENTS_PATH=~/Library/LaunchAgents

    # Stop the services
    launchctl unload $LAUNCH_AGENTS_PATH/com.example.celeryworker.plist
    launchctl unload $LAUNCH_AGENTS_PATH/com.example.nodeapp.http.plist
    for i in $(seq 0 $((${NUM_SERVERS:-1} - 1))); do
        current_port=$((start_port + i))
        echo "Unloading com.example.nodeapp.${server_type}_${current_port}.plist"
        launchctl unload $LAUNCH_AGENTS_PATH/com.example.nodeapp.${server_type}_${current_port}.plist
    done
    launchctl unload $LAUNCH_AGENTS_PATH/com.example.ollama.plist
    brew services stop rabbitmq

    # Remove the service files
    rm $LAUNCH_AGENTS_PATH/com.example.celeryworker.plist
    rm $LAUNCH_AGENTS_PATH/com.example.nodeapp.http.plist
    for i in $(seq 0 $((${NUM_SERVERS:-1} - 1))); do
        current_port=$((start_port + i))
        rm $LAUNCH_AGENTS_PATH/com.example.nodeapp.${server_type}_${current_port}.plist
    done
    rm $LAUNCH_AGENTS_PATH/com.example.ollama.plist

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