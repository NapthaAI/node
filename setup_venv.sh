#!/bin/bash
set -e

# Ensure we're in the conda environment
eval "$(conda shell.bash hook)"
conda activate myenv

# Install dependencies using Poetry
cd /app
poetry install

# Print Python version and path for verification
which python
python --version

echo "Environment setup complete."