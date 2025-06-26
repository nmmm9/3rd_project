# Use the official Python image as a base image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the dependencies
RUN apt-get update && apt-get install -y git \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port the app runs on (필요에 따라 수정)
EXPOSE 5000

# Command to run the application (필요에 따라 수정)
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:5000 --timeout 300 app:app"]