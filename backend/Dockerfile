# Titiler custom API Dockerfile
FROM ghcr.io/developmentseed/titiler:latest

# Install extra dependencies
# cogeo-mosaic  – MosaicJSON creation & memory backend
# boto3         – S3 / R2 client used at startup to list COGs
# titiler.mosaic – mosaic tiling factory & error handlers
RUN pip install \
    "titiler.mosaic" \
    "cogeo-mosaic" \
    "boto3" \
    "rio-tiler[s3]"

# Copy the entire app package
WORKDIR /app
COPY __init__.py  /app/__init__.py
COPY routers.py   /app/routers.py
COPY main.py      /app/main.py

# Entrypoint: run the RouteRadar TiTiler app
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

EXPOSE 8000
