#!/bin/bash

# Log function for better readability
log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1" >> /var/log/rabbitmq_user_setup.log
}

log "Starting RabbitMQ..."
RABBITMQ_NODE_PORT=5672 rabbitmq-server -detached

log "Waiting for RabbitMQ to be ready..."
sleep 10  # Increase if necessary

log "Checking RabbitMQ status..."
rabbitmqctl wait --timeout 60

log "Creating user $RMQ_USER..."
rabbitmqctl add_user "$RMQ_USER" "$RMQ_PASSWORD"

if [ $? -eq 0 ]; then
    rabbitmqctl set_user_tags "$RMQ_USER" administrator
    rabbitmqctl set_permissions -p / "$RMQ_USER" '.*' '.*' '.*'
    log "User $RMQ_USER created successfully."
else
    log "Failed to add user $RMQ_USER."
fi

# Keep the script running to prevent the container from exiting
tail -f /dev/null
