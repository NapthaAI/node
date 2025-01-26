#!/bin/bash

echo "Waiting for PostgreSQL to start..."
sleep 10

# Create user
psql -U postgres -p $LOCAL_DB_POSTGRES_PORT -c "CREATE USER $LOCAL_DB_POSTGRES_USERNAME WITH PASSWORD '$LOCAL_DB_POSTGRES_PASSWORD' CREATEDB;" || true

# Create database
psql -U postgres -p $LOCAL_DB_POSTGRES_PORT -c "CREATE DATABASE $LOCAL_DB_POSTGRES_NAME OWNER $LOCAL_DB_POSTGRES_USERNAME;" || true

# Set permissions
psql -U postgres -p $LOCAL_DB_POSTGRES_PORT -c "GRANT ALL PRIVILEGES ON DATABASE $LOCAL_DB_POSTGRES_NAME TO $LOCAL_DB_POSTGRES_USERNAME;"

# Create a flag file to signal completion
touch /tmp/postgres_initialized