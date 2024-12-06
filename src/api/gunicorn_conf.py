# gunicorn_conf.py
workers = 4  # Number of worker processes
worker_class = 'uvicorn.workers.UvicornWorker'
bind = '0.0.0.0:8000'
loglevel = "info"
accesslog = "-"       # Log access logs to stdout
errorlog = "-"