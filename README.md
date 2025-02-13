# CAR Viewer

## Live car-viewer map
https://car-viewer.streamlit.app


#### Repository with system keep database with SICAR data

CAR is the Brazilian Ambiental Rural Registry which all farms must
register ambiental status and plans.
This is a big (over 200Gb and over 7 million rows) dataset and this project aims to donwload monthly data,
store in postgres and serve by API with a minimal frontend to search and plot data on map.


### Instalation
Using Docker compose

```
cd car-viewer-foss4g
docker compose up -d
```

then check on browser running services on default links

app
http://localhost:8501

api
http://localhost:8000/docs


Using Dockerfile
```
docker build -t etl-image -f Dockerfile.etl .
docker build -t api-image -f Dockerfile.api .
docker build -t app-image -f Dockerfile.app .

# create .env with yours env vars
docker run --name etl-container --network=host --env-file .env etl-image
docker run --name api-container --network=host --env-file .env api-image
docker run --name app-container --network=host --env-file .env app-image
```

check logs with

```
docker logs etl-container

```
