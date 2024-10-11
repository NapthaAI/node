#!/bin/bash

# Set the log file path to be in /var/log
LOG_FILE="/var/log/startup.log"

# Function to log messages with timestamps
log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# Set default values for environment variables
export RMQ_USER=${RMQ_USER:-username}
export RMQ_PASSWORD=${RMQ_PASSWORD:-password}
export HUB_ROOT_USER=${HUB_ROOT_USER:-root}
export HUB_ROOT_PASS=${HUB_ROOT_PASS:-root}
export HUB_USERNAME=${HUB_USERNAME:-seller1}
export HUB_PASSWORD=${HUB_PASSWORD:-great-password}
export DB_ROOT_USER=${DB_ROOT_USER:-root}
export DB_ROOT_PASS=${DB_ROOT_PASS:-root}

log "Starting initialization process"

# Run Hub initialization
log "Running Hub initialization"
if /root/miniforge3/envs/myenv/bin/python /app/node/storage/hub/init_hub.py >> "$LOG_FILE" 2>&1; then
    log "Hub initialization completed"
else
    log "Hub initialization failed" && exit 1
fi

# Run user setup
log "Running user setup"
if /root/miniforge3/envs/myenv/bin/python /app/node/storage/hub/init_hub.py --user >> "$LOG_FILE" 2>&1; then
    log "User setup completed"
else
    log "User setup failed" && exit 1
fi

# Run local db
log "Initializing local database"
if /root/miniforge3/envs/myenv/bin/python /app/node/storage/db/init_db.py >> "$LOG_FILE" 2>&1; then
    log "Local database initialization completed"
else
    log "Local database initialization failed" && exit 1
fi

# Start supervisord using conda
log "Starting supervisord"
exec conda run --no-capture-output -n myenv /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf >> "$LOG_FILE" 2>&1
