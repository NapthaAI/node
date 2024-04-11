# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the Python script into the container
COPY streaming_output.py /usr/src/app

# Command to run when starting the container
CMD ["python", "streaming_output.py"]
