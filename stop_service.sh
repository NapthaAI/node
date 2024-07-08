#!/bin/bash

os=$(uname)
if [ "$os" = "Darwin" ]; then
    # Stop the services
    launchctl unload ~/Library/LaunchAgents/com.example.celeryworker.plist
    launchctl unload ~/Library/LaunchAgents/com.example.nodeapp.plist
    launchctl unload ~/Library/LaunchAgents/com.example.ollama.plist
    brew services stop rabbitmq

    # Remove the service files
    rm ~/Library/LaunchAgents/com.example.celeryworker.plist
    rm ~/Library/LaunchAgents/com.example.nodeapp.plist
    rm ~/Library/LaunchAgents/com.example.ollama.plist

    # Provide feedback
    echo "Services stopped and plist files removed."
else
    # Stop the services
    sudo systemctl stop celeryworker.service
    sudo systemctl stop nodeapp.service
    sudo systemctl stop ollama.service
    sudo systemctl stop rabbitmq-server.service

    # Disable the services
    sudo systemctl disable celeryworker.service
    sudo systemctl disable nodeapp.service
    sudo systemctl disable ollama.service
    sudo systemctl disable rabbitmq-server.service

    # Remove the service files
    sudo rm /etc/systemd/system/celeryworker.service
    sudo rm /etc/systemd/system/nodeapp.service
    sudo rm /etc/systemd/system/ollama.service
    sudo rm /etc/systemd/system/rabbitmq-server.service

    echo "Services stopped and systemd files removed."
fi