#!/bin/bash

# Stop the services
launchctl unload ~/Library/LaunchAgents/com.example.celeryworker.plist
launchctl unload ~/Library/LaunchAgents/com.example.nodeapp.plist
launchctl unload ~/Library/LaunchAgents/com.example.ollama.plist

# Remove the service files
rm ~/Library/LaunchAgents/com.example.celeryworker.plist
rm ~/Library/LaunchAgents/com.example.nodeapp.plist
rm ~/Library/LaunchAgents/com.example.ollama.plist

# Provide feedback
echo "Services stopped and plist files removed."
