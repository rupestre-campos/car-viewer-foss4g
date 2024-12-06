export DBNAME="car"
export USER="postgres"
export PASSWORD="p0stgre5"
export HOST="192.168.0.122"

python tiles.py

scp ../data/area_imovel.pmtiles username@192.168.0.122:/media/username/data1/area_imovel_new.pmtiles

ssh username@192.168.0.122 -f 'mv /media/username/data1/area_imovel.pmtiles /media/username/data1/area_imovel.pmtiles.bkp'
ssh username@192.168.0.122 -f 'mv /media/username/data1/area_imovel_new.pmtiles /media/username/data1/area_imovel.pmtiles'
