# Titiler custom API Dockerfile — AWS Lambda (container image)
FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies (ex: GDAL)
RUN yum update -y && \
    yum install -y expat && \
    mkdir -p /opt/lib && \
    cp -a /usr/lib64/libexpat.so.1* /opt/lib/ && \
    yum clean all

# Install dependencies into the Lambda task root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY __init__.py  ${LAMBDA_TASK_ROOT}/__init__.py
COPY routers.py   ${LAMBDA_TASK_ROOT}/routers.py
COPY main.py      ${LAMBDA_TASK_ROOT}/main.py

# GDAL/VSI tuning — baked into the image so these apply in both Lambda
# and the docker-compose local stack without duplication.
ENV GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR \
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.tiff,.vrt,.ovr \
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES \
    GDAL_HTTP_MULTIPLEX=YES \
    GDAL_HTTP_VERSION=2 \
    GDAL_BAND_BLOCK_CACHE=HASHSET \
    GDAL_CACHEMAX=512 \
    CPL_VSIL_CURL_CACHE_SIZE=200000000 \
    VSI_CACHE=TRUE \
    VSI_CACHE_SIZE=536870912

# Lambda invokes main.handler (the Mangum wrapper around the FastAPI app)
CMD ["main.handler"]
