# CAR Viewer

## Living DEMO
https://car-viewer.streamlit.app


#### Repository with tools to deal with CAR data

CAR is the Brazilian Ambiental Rural Registry which all farms must
register ambiental status and plans.

### Overview
src/etl/etl.py is the ETL getting data and inserting into a postgis database.

src/api/server.py is the API to access database to search data.

src/app/home.py is the frontend app to deal with data, search, plot and downloads


NOTE: It is not a easy to deploy, ready to use application.
There are many parts, so understand it and make apropriate changes.
Call me if needs any help! ;)

### Simple workflow for ubuntu

on the main server
```
sudo apt update
sudo apt install build-essential libsqlite3-dev zlib1g-dev \
    tesseract-ocr postgresql postgis wget gdal-bin libgdal-dev
```

setup postgres with your password
```
sudo -u postgres psql
ALTER USER postgres PASSWORD 'newpassword';
\q
```

setup go-pmtiles
choose suitable release on https://github.com/protomaps/go-pmtiles/releases/

```
mkdir go-pmtiles
cd go-pmtiles
wget https://github.com/protomaps/go-pmtiles/releases/download/v1.20.0/go-pmtiles_1.20.0_Linux_arm64.tar.gz
tar -xvzf go-pmtiles_1.20.0_Linux_arm64.tar.gz
sudo cp pmtiles /usr/local/bin/pmtiles
```

on the worker for tile creation

```
sudo apt update
sudo apt install build-essential libsqlite3-dev zlib1g-dev \
    gdal-bin libgdal-dev

git clone https://github.com/felt/tippecanoe.git
cd tippecanoe
sudo make -j
sudo make install
```
