import os
import json

from collections import defaultdict

from datetime import datetime, timedelta, timezone
import jwt
import asyncpg

from asyncpg.pool import Pool
from itertools import chain

import asyncio
import uvicorn

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
from pydantic import BaseModel, constr

from starlette.responses import Response
from starlette.middleware.cors import CORSMiddleware

import httpx

from render_car import create_pdf_from_geojson, create_kmz_from_geojson, create_shapefile_from_geojson

query_timeout = int(os.getenv("QUERY_TIMEOUT", "30"))

DATABASE_HOST = os.getenv("POSTGRES_HOST", "localhost")
DATABASE_PORT = os.getenv("POSTGRES_PORT", "5432")
DATABASE_NAME = os.getenv("POSTGRES_DB", "car")
DATABASE_USER = os.getenv("POSTGRES_USER", "postgres")
DATABASE_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

PMTILES_SERVER_URL = os.getenv("PMTILES_SERVER_URL", "http://localhost:8081")
API_KEYS = os.getenv("API_KEYS", "1234,5678").split(",")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "ABCD")
JWT_VALID_SECONDS = os.getenv("JWT_VALID_SECONDS", "3600")

API_KEY_QUERY_NAME = os.getenv("API_KEY_QUERY_NAME", "API_KEY")
api_key_query = APIKeyQuery(name=API_KEY_QUERY_NAME, auto_error=False)

app = FastAPI(root_path="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


db_pool: Pool = None

httpx_client = httpx.AsyncClient()

async def init_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(
            user=DATABASE_USER,
            password=DATABASE_PASSWORD,
            database=DATABASE_NAME,
            host=DATABASE_HOST,
            port=DATABASE_PORT,
            min_size=1,
            max_size=10  # Tune this based on Raspberry Pi memory
        )

async def get_db_conn():
    global db_pool
    if db_pool is None:
        await init_db_pool()
    return await db_pool.acquire()

from contextlib import asynccontextmanager

@asynccontextmanager
async def get_temp_conn():
    conn = await get_db_conn()
    try:
        yield conn
    finally:
        await db_pool.release(conn)

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

def create_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.now(tz=timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm="HS256")
    return encoded_jwt

def verify_token_from_query(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
        if payload["sub"] != "tiles_access":
            raise HTTPException(status_code=403, detail="Invalid token")
        return True
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

with open("map.html", "r") as file:
    html_template = file.read()

@app.get("/", include_in_schema=False)
async def serve_main_page():
    token = create_token()
    html_content = html_content.replace("{{TOKEN}}", token)

@app.get("/get-token")
async def get_token(api_key: APIKey = Depends(get_api_key)):
    token_expires = timedelta(seconds=JWT_VALID_SECONDS)  # Token valid for 1 day
    token = create_token({"sub": "tiles_access"}, expires_delta=token_expires)

    return {"token": token}

@app.get("/list-layers")
async def list_layers(token: str = Query(..., description="Map token required for access")):
    if not token:
        raise HTTPException(status_code=400, detail="TOKEN is required")
    verify_token_from_query(token)

    try:
        async with get_temp_conn() as conn:
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
    file_format: str = Path(..., description="Format of the response: 'geojson', 'kmz' 'shp' or 'pdf'", pattern="^(geojson|pdf|kmz|shp)$"),
    layer: str = Query(None, description="Optional layer to fetch data from"),
    token: str = Query(..., description="token required for access")
):

    if not token:
        raise HTTPException(status_code=400, detail="TOKEN is required")

    verify_token_from_query(token)

    car_code = ''.join([char.upper() for char in car_code if char.isalnum() or char == "-"])
    params = CodImovelModel(car_code=car_code)
    state_code = params.car_code[:2]

    conn = await get_db_conn()

    layer_filter = ""
    if layer:
        layer_value = ''.join([char.upper() for char in layer[:256] if char.isalpha() or char=='_'])
        layer_filter = f" AND layer = '{layer_value}' "


    async with get_temp_conn() as conn:
        theme_tables = await conn.fetch(
            f"""
            SELECT DISTINCT ON (state_code, layer)
                layer
            FROM car_statistics
            WHERE state_code = $1
            {layer_filter}
            ORDER BY state_code, layer, release_date DESC
            """,
            state_code
        )


    if not theme_tables:
        raise HTTPException(status_code=404, detail="Layer not found")

    table_names = [f"{table['layer']}_{state_code.lower()}" for table in theme_tables]

    async def fetch_table_features(table_name: str):
        async with get_temp_conn() as conn:
            query = f"""
                SELECT
                    ST_AsGeoJSON(geom)::jsonb as geom_json,
                    properties
                FROM {table_name}
                WHERE car_code = $1
            """
            return await conn.fetch(query, params.car_code)

    try:
        feature_results = await asyncio.wait_for(
            asyncio.gather(*[fetch_table_features(tbl) for tbl in table_names]),
            timeout=query_timeout
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Database query timeout")

    geojson_features = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": json.loads(row["geom_json"]),
                "properties": json.loads(row["properties"]),
            }
            for row in chain.from_iterable(feature_results)
        ]
    }

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

    elif file_format == "shp":
        shp_zip_bytes = create_shapefile_from_geojson(geojson_features, car_code)
        return Response(
            content=shp_zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={car_code}.zip"}
        )

    raise HTTPException(status_code=400, detail="Unsupported format requested")

@app.post("/intersecting-perimeters")
async def intersecting_perimeters(
    point: PointModel,
    token: str = Query(..., description="token required for access")
):

    if not token:
        raise HTTPException(status_code=400, detail="TOKEN is required")

    verify_token_from_query(token)

    point_geometry = f"ST_SetSrid(ST_MakePoint({point.longitude}, {point.latitude}), 4326)"

    intersecting_perimeters = []

    table_name = "area_imovel"
    try:
        async with get_temp_conn() as conn:

            features = await asyncio.wait_for(
                conn.fetch(
                    f'SELECT ST_AsGeoJSON(geom)::jsonb as geom_json, properties FROM {table_name} WHERE ST_Intersects(geom, {point_geometry})',
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

        geojson_response = {
            "type": "FeatureCollection",
            "features": intersecting_perimeters
        }

        return geojson_response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tiles/{z}/{x}/{y}.pbf")
async def get_tile(z: int, x: int, y: int, token: str = Query(..., description="token required for access")):
    """Get area_imovel layer as Vector Tiles."""

    if not token:
        raise HTTPException(status_code=400, detail="TOKEN is required")

    # Verify the token from the query param
    verify_token_from_query(token)

    pmtiles_url = f"{PMTILES_SERVER_URL}/area_imovel/{z}/{x}/{y}.mvt"

    try:
        response = await httpx_client.get(pmtiles_url)
        response.raise_for_status()
        return Response(content=response.content, media_type='application/x-protobuf')
    except httpx.RequestError as e:
        raise HTTPException(status_code=404, detail=f"Tile not found: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)
