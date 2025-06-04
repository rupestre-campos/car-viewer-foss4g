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

# create .env with yours env vars
docker run -d --name etl-container --restart=unless-stopped --network=host --env-file .env etl-image
docker run -d --name api-container --restart=unless-stopped --network=host --env-file .env api-image
```

check logs with

```
docker logs etl-container
```
## Setup HTTPS

Install and enable nginx and install certbot

```
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx
sudo systemctl enable nginx
```

Configure Nginx as reverse proxy

```
sudo nano /etc/nginx/sites-available/api
```
add the following content, remember to replace yourdomain.com bellow by your real domain

```
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

then create symlink, test config and restart nginx

```
sudo ln -s /etc/nginx/sites-available/api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

Now obtain a free SSL certificate, you must first configure DNS to point to the machine IP, then run bellow code.
Remember to replace yourdomain.com bellow by your real domain

```
sudo certbot --nginx -d yourdomain.com
# Follow the prompts to complete the SSL setup.

# Check automatic renew with
sudo certbot renew --dry-run

# Create crontab to autorenew
echo "0 3 * * * root certbot renew --quiet && systemctl reload nginx" | sudo tee -a /etc/crontab > /dev/null
```

Now with certificates, enable https in nginx by editing config

```
sudo nano /etc/nginx/sites-available/api
```

And add the following content, remember to replace yourdomain.com by your real domain

```
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Then test config and restart nginx to reload

```
sudo nginx -t
sudo systemctl restart nginx
```

## Setup Postgres

Install postgres

```
sudo apt update && sudo apt install -y postgresql postgresql-contrib

# Check service status
sudo systemctl status postgresql

# Enable at startup
sudo systemctl enable postgresql
```

Change postgres user password

```
sudo -u postgres psql

# In psql run this query
ALTER USER postgres WITH PASSWORD 'NEW_PASSWORD';

# then type
\q
```

and update your .env credentials file
