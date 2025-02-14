### Dockerfile for API (src/api/server.py)
FROM python:3.10-slim

# Install system dependencies
RUN apt update && apt install -y \
    build-essential \
    python3-dev  && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY src/app /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose API port
EXPOSE 8501

# Run the API server
CMD ["streamlit", "run", "home.py", "--server.port=8501"]
