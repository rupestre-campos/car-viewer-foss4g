import os

ip_proxy = os.getenv("IP_PORT_PROXY", None)
host = os.getenv("DB_HOST", "localhost")
port = os.getenv("DB_PORT", "5432")
dbname = os.getenv("DB_NAME", "car")
user = os.getenv("DB_USER", "postgres")
password = os.getenv("DB_PASSWORD", "postgres")
