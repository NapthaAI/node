#!/bin/bash

echo "Waiting for PostgreSQL to start..."
sleep 10

# Create user
psql -U postgres -p $LOCAL_DB_PORT -c "CREATE USER $LOCAL_DB_USER WITH PASSWORD '$LOCAL_DB_PASSWORD' CREATEDB;" || true

# Create database
psql -U postgres -p $LOCAL_DB_PORT -c "CREATE DATABASE $LOCAL_DB_NAME OWNER $LOCAL_DB_USER;" || true

# Set permissions
psql -U postgres -p $LOCAL_DB_PORT -c "GRANT ALL PRIVILEGES ON DATABASE $LOCAL_DB_NAME TO $LOCAL_DB_USER;"

# Create a flag file to signal completion
touch /tmp/postgres_initialized