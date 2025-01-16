export DB_HOST="192.168.0.122"
export DB_PORT="5432"
export DB_NAME="car"
export DB_USER="postgres"
export DB_PASSWORD="p0stgre5"
# squid local proxy
export IP_PORT_PROXY="http://127.0.0.1:3128"

python etl_sicar.py
