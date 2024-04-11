# Use python base image
FROM python:3.10-slim

# Install gcc, pythondev and other dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy all files from the current directory into the container
COPY . .

# Install dependencies
RUN pip install -r requirements.txt

# Execute download script
RUN python download.py