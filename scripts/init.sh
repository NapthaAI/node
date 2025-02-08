#!/bin/bash
# File: ./scripts/init.sh
set -e

# Create 'naptha' database if it doesn't exist
if ! psql -U "$POSTGRES_USER" -lqt | cut -d \| -f 1 | grep -qw naptha; then
  echo "Creating database: naptha"
  psql -U "$POSTGRES_USER" -c "CREATE DATABASE naptha;"
fi

# Create 'litellm' database if it doesn't exist
if ! psql -U "$POSTGRES_USER" -lqt | cut -d \| -f 1 | grep -qw litellm; then
  echo "Creating database: litellm"
  psql -U "$POSTGRES_USER" -c "CREATE DATABASE litellm;"
fi
