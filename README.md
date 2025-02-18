# CAR Viewer

SICAR is the Brazilian Ambiental Rural Registry System which all farms must
register ambiental status and plans.
This is a big (over 200Gb and over 7 million rows) dataset and this project aims to donwload monthly data,
store in postgres and serve by API with a minimal frontend to search and plot data on map.
There is a PMTiles basemap with all polygons, being in development .

## Demo car-viewer map app
https://car-viewer.streamlit.app

### Instalation
Using Docker compose

```
cd car-viewer-foss4g
docker compose up -d
```

then check on browser localhost on ports 8501 and 8000.
Database on port 5433. For database you may change passwords.

Using Dockerfile
```
docker build -t etl-image -f Dockerfile.etl .
docker build -t api-image -f Dockerfile.api .
docker build -t app-image -f Dockerfile.app .

# create .env with yours env vars
docker run -d --name etl-container --restart=unless-stopped --network=host --env-file .env etl-image
docker run -d --name api-container --restart=unless-stopped --network=host --env-file .env api-image
docker run -d --name app-container --restart=unless-stopped --network=host --env-file .env app-image
```

check logs with

```
docker logs etl-container

```
