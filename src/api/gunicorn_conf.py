import os

# Get environment variables with defaults
workers = int(os.getenv("GUNICORN_WORKERS", "4"))  # Default to 4 workers
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "uvicorn.workers.UvicornWorker")
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")  # Default to stdout
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")  # Default to stderr
