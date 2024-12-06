import os
import json
import httpx
import asyncpg
import asyncio
import uvicorn
from typing import Dict
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import jwt
import random
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Security,
    Query,
    Path
)
from fastapi.security.api_key import (
    APIKeyQuery,
    APIKey
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, constr

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.middleware.cors import CORSMiddleware

import secrets_config as secret
from render_car import create_pdf_from_geojson, create_kmz_from_geojson

PMTILES_PORT = 8081
query_timeout = 30

# Replace with your actual PostgreSQL connection details
DATABASE_NAME = secret.dbname
DATABASE_USER = secret.user
DATABASE_PASSWORD = secret.password
DATABASE_HOST = secret.host
DATABASE_PORT = secret.port

API_KEYS = secret.api_keys
MAP_TOKENS_NO_EXPIRY = secret.map_tokens_no_expiry

nicfi_api_key = secret.nicfi_api_key
SECRET_KEY = secret.secret_key
JWT_VALID_SECONDS = 3600

API_KEY_NAME = "API_KEY"
api_key_query = APIKeyQuery(name=API_KEY_NAME, auto_error=False)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


httpx_client = httpx.AsyncClient()

async def get_db_conn():
    conn = await asyncpg.connect(
        user=DATABASE_USER,
        password=DATABASE_PASSWORD,
        database=DATABASE_NAME,
        host=DATABASE_HOST,
        port=DATABASE_PORT
    )
    return conn

class StateModel(BaseModel):
    state: constr(strip_whitespace=True, min_length=2, max_length=2)

class MunicipalityModel(BaseModel):
    state: constr(strip_whitespace=True, min_length=2, max_length=2)
    municipality: constr(strip_whitespace=True, min_length=1, max_length=10)

class CodImovelModel(BaseModel):
    car_code: constr(strip_whitespace=True, min_length=40, max_length=43)

class PointModel(BaseModel):
    latitude: float
    longitude: float

def get_api_key(
    api_key_query: str = Security(api_key_query),
):
    if api_key_query in API_KEYS:
        return api_key_query
    else:
        raise HTTPException(status_code=403, detail="Could not validate credentials")

# Helper function to create a JWT token
def create_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.now(tz=timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    return encoded_jwt

# Dependency to verify the JWT token from the query parameter
def verify_token_from_query(map_key: str):
    if map_key in MAP_TOKENS_NO_EXPIRY:
        return True
    try:
        payload = jwt.decode(map_key, SECRET_KEY, algorithms=["HS256"])
        if payload["sub"] != "tiles_access":
            raise HTTPException(status_code=403, detail="Invalid token")
        return True
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/", include_in_schema=False)
async def redirect():
    url = secret.frontend_url
    response = RedirectResponse(url=url)
    return response

@app.get("/list-layers")
async def list_layers(api_key: APIKey = Depends(get_api_key)):
    try:
        conn = await get_db_conn()
        query = """
        SELECT distinct on (state_code, layer)
        state_code, layer, release_date, count_active_features, created_at
        FROM car_statistics
        ORDER BY state_code, layer, release_date DESC
        """
        results = await conn.fetch(query)
        await conn.close()
        layers = defaultdict(dict)
        for record in results:
            layers[record["state_code"]][record["layer"]] = {
                "release_date": record["release_date"].isoformat(),
                "feature_count": record["count_active_features"],
                "download_date": record["created_at"]
            }
        return layers

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/layers/{car_code}.{file_format}")
async def get_layers(
    car_code: str,
    file_format: str = Path(..., description="Format of the response: 'geojson', 'kmz' or 'pdf'", pattern="^(geojson|pdf|kmz)$"),
    api_key: APIKey = Depends(get_api_key),
    layer: str = Query(None, description="Optional layer to fetch data from"),
):
    car_code = ''.join([char.upper() for char in car_code if char.isalnum() or char == "-"])
    params = CodImovelModel(car_code=car_code)
    state_code = params.car_code[:2]

    conn = await get_db_conn()

    layer_filter = ""
    if layer:
        layer_value = ''.join([char.upper() for char in layer[:256] if char.isalpha() or char=='_'])
        layer_filter = f" AND layer = '{layer_value}' "

    theme_tables = await conn.fetch(
        f"""
            SELECT distinct on (state_code, layer)
            layer
            FROM car_statistics
            WHERE state_code = $1
            {layer_filter}
            ORDER BY state_code, layer, release_date Desc
        """, state_code
    )

    if not theme_tables:
        await conn.close()
        raise HTTPException(status_code=404, detail="Layer not found")
    geojson_features = {"type": "FeatureCollection", "features": []}
    query_parts = []
    for table in theme_tables:
        query_parts.append(
            f"""
            SELECT
                ST_AsGeoJSON(geom)::jsonb as geom_json,
                properties
            FROM
                {table['layer']}_{state_code.lower()}
            WHERE car_code = $1 AND active = 1
            """
        )

    union_query = " UNION ALL ".join(query_parts)

    features = await asyncio.wait_for(
        conn.fetch(union_query, params.car_code),
        timeout=query_timeout
    )

    for feature in features:
        geojson_feature = {
            "type": "Feature",
            "geometry": json.loads(feature["geom_json"]),
            "properties": json.loads(feature["properties"])
        }
        geojson_features["features"].append(geojson_feature)

    await conn.close()

    if len(geojson_features["features"]) == 0:
        raise HTTPException(status_code=404, detail="CAR not found")

    if file_format == "pdf":
        pdf_file_bytes = create_pdf_from_geojson(geojson_features, car_code)
        return Response(
            content=pdf_file_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={car_code}.pdf"}
        )

    elif file_format == "kmz":
        pdf_file_bytes = create_kmz_from_geojson(geojson_features, car_code)
        return Response(
            content=pdf_file_bytes,
            media_type="application/vnd.google-earth.kmz",
            headers={"Content-Disposition": f"attachment; filename={car_code}.kmz"}
        )
    elif file_format == "geojson":
        return geojson_features
    else:
        raise HTTPException(status_code=400, detail="Unsupported format requested")

@app.post("/intersecting-perimeters")
async def intersecting_perimeters(
    point: PointModel,
    api_key: APIKey = Depends(get_api_key)
):

    table_name = "area_imovel"
    try:
        conn = await get_db_conn()

        # Construct the point geometry in PostGIS format
        point_geometry = f"ST_SetSrid(ST_MakePoint({point.longitude}, {point.latitude}), 4326)"

        # Query all states for intersecting perimeters
        intersecting_perimeters = []


        # Perform the intersection query
        features = await asyncio.wait_for(
            conn.fetch(
                f'SELECT ST_AsGeoJSON(geom)::jsonb as geom_json, properties FROM {table_name} WHERE active = 1 and ST_Intersects(geom, {point_geometry})',
                timeout=query_timeout
            ),
            timeout=query_timeout
        )

        for feature in features:
            geojson_feature = {
                "type": "Feature",
                "geometry": json.loads(feature["geom_json"]),
                "properties": json.loads(feature["properties"])
            }
            intersecting_perimeters.append(geojson_feature)


        await conn.close()

        # Construct the GeoJSON FeatureCollection response
        geojson_response = {
            "type": "FeatureCollection",
            "features": intersecting_perimeters
        }

        return geojson_response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint to get a token by providing an API key
@app.get("/get-map-token")
async def get_token(api_key: APIKey = Depends(get_api_key)):
    token_expires = timedelta(seconds=JWT_VALID_SECONDS)  # Token valid for 1 day
    token = create_token({"sub": "tiles_access"}, expires_delta=token_expires)

    return {"token": token}

@app.get("/tiles/{z}/{x}/{y}.pbf")
async def get_tile(z: int, x: int, y: int, map_token: str = Query(..., description="Map token required for access")):
    """Get area_imovel layer as Vector Tiles."""

    if not map_token:
        raise HTTPException(status_code=400, detail="MAP_TOKEN is required")

    # Verify the token from the query param
    verify_token_from_query(map_token)

    pmtiles_url = f"http://localhost:{PMTILES_PORT}/area_imovel/{z}/{x}/{y}.mvt"

    try:
        response = await httpx_client.get(pmtiles_url)
        response.raise_for_status()
        return Response(content=response.content, media_type='application/x-protobuf')
    except httpx.RequestError as e:
        raise HTTPException(status_code=404, detail=f"Tile not found: {e}")

def get_random_subdomain():
    """
    Returns a random subdomain from tiles0 to tiles3.
    """
    subdomains = ["tiles0", "tiles1", "tiles2", "tiles3"]
    return random.choice(subdomains)

@app.get("/image-tiles/{z}/{x}/{y}.png")
async def get_tile(z: int, x: int, y: int, map_token: str = Query(..., description="Map token required for access")):
    """Get nicfi images layer from planet."""

    if not map_token:
        raise HTTPException(status_code=400, detail="MAP_TOKEN is required")

    # Verify the token from the query param
    verify_token_from_query(map_token)
    subdomain = get_random_subdomain()
    tiles_url = f"https://{subdomain}.planet.com/basemaps/v1/planet-tiles/planet_medres_visual_2024-10_mosaic/gmap/{z}/{x}/{y}.png?api_key={nicfi_api_key}"

    try:
        response = await httpx_client.get(tiles_url)
        response.raise_for_status()
        return Response(content=response.content, media_type='image/png')
    except httpx.RequestError as e:
        raise HTTPException(status_code=404, detail=f"Tile not found: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
