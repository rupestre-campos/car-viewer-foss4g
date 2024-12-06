import os

host = os.getenv("DB_HOST", "localhost")
port = os.getenv("DB_PORT", "5432")
dbname = os.getenv("DB_NAME", "car")
user = os.getenv("DB_USER", "postgres")
password = os.getenv("DB_PASSWORD", "postgres")

api_keys = os.getenv("API_KEYS", "1234,5678").split(",")
map_tokens_no_expiry = os.getenv("MAP_TOKENS_NO_EXPIRY", "abcd,defg").split(",")
secret_key = os.getenv("SECRET_KEY", "123456")

api_base_url = os.getenv("API_URL", "http://192.168.0.1:8000")

frontend_url = os.getenv("FRONTEND_URL", "https://car-viewer.streamlit.app/")

nicfi_api_key = os.getenv("NICFI_API_KEY", "12345")
