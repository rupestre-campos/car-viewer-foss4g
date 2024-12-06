import os

api_key = os.getenv("API_KEY", "1234")
api_base_url = os.getenv("API_URL", "http://192.168.0.1:8000")

cache_ttl = int(os.getenv("CACHE_TTL", "300"))
cache_ttl_get_layers  = int(os.getenv("CACHE_TTL_GET_LAYERS", "86400"))

default_car_code = os.getenv("DEFAULT_CAR_CODE", "GO-5200134-EE6AF190BD1A4F9186C4717653B7E81E")
api_contact_url = os.getenv("CONTACT_URL", "https://car.rupestre-campos.org/contact")
