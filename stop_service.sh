#!/bin/bash

# Stop the service
sudo systemctl stop celeryworker.service
sudo systemctl stop nodeapp.service
sudo systemctl stop ollama.service

# Remove the service
sudo systemctl disable celeryworker.service
sudo systemctl disable nodeapp.service
sudo systemctl disable ollama.service

# Remove the service files
sudo rm /etc/systemd/system/celeryworker.service
sudo rm /etc/systemd/system/nodeapp.service
sudo rm /etc/systemd/system/ollama.service
