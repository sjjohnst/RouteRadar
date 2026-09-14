# TiTiler backed API — one file, two targets:
#   docker build .                 → Lambda image (default, last stage)
#   docker build --target dev .    → local dev image (uvicorn + live-reload)
#
# Both targets share the `deps` stage, so local dev resolves and runs the
# exact same dependency set, Python version, and GDAL tuning as production —
# a single source of truth instead of two.
ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.10.9
ARG GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
ARG CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.tiff,.vrt,.ovr,.json
ARG GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES
ARG GDAL_HTTP_MULTIPLEX=YES
ARG GDAL_HTTP_VERSION=2
ARG GDAL_BAND_BLOCK_CACHE=HASHSET
ARG GDAL_CACHEMAX=512
ARG CPL_VSIL_CURL_CACHE_SIZE=50000000

# COPY --from doesn't support ARG expansion directly (only FROM does), so the
# uv image needs its own named stage to pin ${UV_VERSION}.
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------------------------------------------------------------------------
# deps — resolve and strip Python dependencies. Shared by every target below.
# ---------------------------------------------------------------------------
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:${PYTHON_VERSION} AS deps

# Global ARGs are only visible to FROM/COPY --from by default — re-declare to
# use it in a RUN below.
ARG PYTHON_VERSION

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /tmp

# findutils/binutils for the strip steps below (find, xargs, strip) — the
# base image doesn't include them. Every dependency here ships a manylinux
# wheel for cp312, so no compiler is needed (verified with `pip install
# --dry-run --only-binary=:all:`) — the old Dockerfile's `dnf install
# gcc-c++` was only ever providing these two as transitive deps.
RUN dnf install -y findutils binutils && dnf clean all

# Use uv to pin python version and dependencies
COPY pyproject.toml uv.lock ./

RUN uv export --no-dev -o requirements-prod.txt
RUN uv export -o requirements-dev.txt

RUN uv pip sync requirements-prod.txt --target /asset --no-binary pydantic --compile-bytecode --python ${PYTHON_VERSION}

# Reduce package size — strip pyc files, remove sources, strip shared libs, remove test dirs
RUN cd /asset && find . -type f -name '*.pyc' | while read f; do n=$(echo $f | sed 's/__pycache__\///' | sed 's/.cpython-[0-9]*//'); cp $f $n; done;
RUN cd /asset && find . -type d -a -name '__pycache__' -print0 | xargs -0 rm -rf
RUN cd /asset && find . -type f -a -name '*.py' -print0 | xargs -0 rm -f
RUN cd /asset && find . -type f -name '*.so*' -not -path "*/numpy.libs/*" -exec strip --strip-unneeded {} \; 2>/dev/null || true
RUN find /asset -type d -a -name 'tests' -print0 | xargs -0 rm -rf
# boto3/botocore aren't installed above — the Lambda runtime already provides
# them (state.py imports the runtime's copy) — so there's nothing to remove
# here beyond the other build cruft.
RUN rm -rdf /asset/numpy/doc/ /asset/bin /asset/geos_license /asset/Misc

# ---------------------------------------------------------------------------
# lambda-build — deps + application code + smoke test. Not shipped itself;
# the final stage below copies only /asset out of it.
# ---------------------------------------------------------------------------
FROM deps AS lambda-build

COPY __init__.py  /asset/__init__.py
COPY r2_env.py    /asset/r2_env.py
COPY state.py     /asset/state.py
COPY routers.py   /asset/routers.py
COPY main.py      /asset/main.py

# Smoke test — verify all imports resolve without starting the app or
# touching any external services (no lifespan, no env vars required).
WORKDIR /asset
RUN python -c "\
import cogeo_mosaic; \
import rasterio; \
import boto3; \
import mangum; \
import fastapi; \
import titiler.core; \
import titiler.mosaic; \
from cogeo_mosaic.backends.memory import MemoryBackend; \
from titiler.mosaic.factory import MosaicTilerFactory; \
import state; \
print('All Good')"

# ---------------------------------------------------------------------------
# dev — uvicorn + live-reload, run via docker-compose (target: dev).
# WORKDIR is /app to match the bind mount (./backend:/app in compose):
# without it, uvicorn would resolve "main:app" against the baked-in copy
# below instead of the mounted source, and --reload would silently do nothing.
# ---------------------------------------------------------------------------
FROM deps AS dev

ARG PYTHON_VERSION
RUN uv pip sync /tmp/requirements-dev.txt --target /asset --no-binary pydantic --compile-bytecode --python ${PYTHON_VERSION}

WORKDIR /app
COPY __init__.py r2_env.py state.py routers.py main.py ./

ARG GDAL_DISABLE_READDIR_ON_OPEN
ARG CPL_VSIL_CURL_ALLOWED_EXTENSIONS
ARG GDAL_HTTP_MERGE_CONSECUTIVE_RANGES
ARG GDAL_HTTP_MULTIPLEX
ARG GDAL_HTTP_VERSION
ARG GDAL_BAND_BLOCK_CACHE
ARG GDAL_CACHEMAX
ARG CPL_VSIL_CURL_CACHE_SIZE
ENV PYTHONPATH=/asset \
    GDAL_DISABLE_READDIR_ON_OPEN=${GDAL_DISABLE_READDIR_ON_OPEN} \
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=${CPL_VSIL_CURL_ALLOWED_EXTENSIONS} \
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=${GDAL_HTTP_MERGE_CONSECUTIVE_RANGES} \
    GDAL_HTTP_MULTIPLEX=${GDAL_HTTP_MULTIPLEX} \
    GDAL_HTTP_VERSION=${GDAL_HTTP_VERSION} \
    GDAL_BAND_BLOCK_CACHE=${GDAL_BAND_BLOCK_CACHE} \
    GDAL_CACHEMAX=${GDAL_CACHEMAX} \
    CPL_VSIL_CURL_CACHE_SIZE=${CPL_VSIL_CURL_CACHE_SIZE}

EXPOSE 8000
# The base image bakes in ENTRYPOINT ["/lambda-entrypoint.sh"] (the Lambda
# Runtime Interface Client), which otherwise runs `lambda-entrypoint.sh
# python -m uvicorn ...` and rejects "python" as an invalid handler name.
# Reset it so CMD runs directly, as a normal server process.
ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---------------------------------------------------------------------------
# Final stage (default target) — clean Lambda base plus only /asset.
# Nothing lambda-build/deps needed (a compiler, pip's cache, intermediate
# files the strip steps remove) ends up in the shipped image or its layer
# history, since only /asset is copied across the stage boundary.
# ---------------------------------------------------------------------------
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:${PYTHON_VERSION}

# rasterio needs libexpat.so.1 at runtime, which this base image doesn't ship.
# Ref: https://github.com/developmentseed/titiler/discussions/1108#discussioncomment-13045681
RUN dnf install -y expat && dnf clean all

COPY --from=lambda-build /asset /asset

# GDAL/VSI tuning — baked into the image so these apply in both Lambda
# and the docker-compose local stack without duplication.
ARG GDAL_DISABLE_READDIR_ON_OPEN
ARG CPL_VSIL_CURL_ALLOWED_EXTENSIONS
ARG GDAL_HTTP_MERGE_CONSECUTIVE_RANGES
ARG GDAL_HTTP_MULTIPLEX
ARG GDAL_HTTP_VERSION
ARG GDAL_BAND_BLOCK_CACHE
ARG GDAL_CACHEMAX
ARG CPL_VSIL_CURL_CACHE_SIZE
ENV PYTHONPATH=/asset \
    GDAL_DISABLE_READDIR_ON_OPEN=${GDAL_DISABLE_READDIR_ON_OPEN} \
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=${CPL_VSIL_CURL_ALLOWED_EXTENSIONS} \
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=${GDAL_HTTP_MERGE_CONSECUTIVE_RANGES} \
    GDAL_HTTP_MULTIPLEX=${GDAL_HTTP_MULTIPLEX} \
    GDAL_HTTP_VERSION=${GDAL_HTTP_VERSION} \
    GDAL_BAND_BLOCK_CACHE=${GDAL_BAND_BLOCK_CACHE} \
    GDAL_CACHEMAX=${GDAL_CACHEMAX} \
    CPL_VSIL_CURL_CACHE_SIZE=${CPL_VSIL_CURL_CACHE_SIZE}

WORKDIR /asset

# Lambda invokes main.handler (the Mangum wrapper around the FastAPI app)
CMD ["main.handler"]
