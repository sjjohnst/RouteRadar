"""app.

app/main.py

Serves COG mosaic tiles and elevation data from Cloudflare R2 via TiTiler.
The MosaicJSON is pre-built by ingestion/build_mosaic.py and fetched lazily
on the first request to each Lambda container (see state.py).
"""

import os
import logging
from contextlib import asynccontextmanager

# --- CLOUDFLARE R2 WORKAROUND ---
# Lambda env vars can't use the standard AWS_* names (they're reserved),
# so we inject our R2 keys from R2_* vars before anything imports boto3/GDAL.
# We also clear AWS_SESSION_TOKEN (set by the Lambda IAM role) because R2
# doesn't support STS session tokens, and we set GDAL S3 config as real OS
# env vars (rasterio ≥1.4 blocks setting AWS_* creds via rasterio.Env).
if "R2_ACCESS_KEY_ID" in os.environ:
    os.environ["AWS_ACCESS_KEY_ID"]     = os.environ["R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ["R2_SECRET_ACCESS_KEY"]
    # R2 only accepts its own region slugs (auto, wnam, enam, …), not AWS
    # region names. Lambda injects AWS_REGION=ca-central-1; unset it entirely
    # so GDAL/boto3 don't send it to R2. We pass region_name="auto" explicitly
    # in our boto3 client (state.py), and GDAL uses the endpoint URL directly.
    os.environ.pop("AWS_REGION", None)
    os.environ.pop("AWS_DEFAULT_REGION", None)

# Always clear the session token so GDAL/boto3 don't send it to R2.
os.environ.pop("AWS_SESSION_TOKEN", None)

# Set GDAL S3 driver config as real OS env vars — rasterio.Env blocks AWS_*
# credential vars in newer versions, but GDAL reads these from the process env.
_r2_endpoint_raw = os.environ.get("R2_S3_ENDPOINT", "")
if _r2_endpoint_raw:
    os.environ["AWS_S3_ENDPOINT"]      = _r2_endpoint_raw.replace("https://", "")
os.environ["AWS_VIRTUAL_HOSTING"]      = "NO"
os.environ["AWS_HTTPS"]                = "YES"

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from rio_tiler.profiles import img_profiles
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.core.middleware import CacheControlMiddleware
from titiler.mosaic.errors import MOSAIC_STATUS_CODES

from routers import mosaic
from state import load_state

# Root log config for the process; modules get their own "routeradar.titiler" logger.
logging.basicConfig(level=logging.INFO)

# Lossless webp for relief tiles - better compression than png, while still being lossless
img_profiles["webp"] = {"quality": 100, "lossless": True}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """No-op lifespan — state is loaded lazily on first request."""
    yield


app = FastAPI(
    title="RouteRadar TiTiler",
    description="Serves slope COG tiles from Cloudflare R2.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Cache-Control for tile responses.
#
# Without this there is no Cache-Control header at all, so the browser refetches
# every tile on every pan and no CDN will hold them — the single cheapest win
# available on the serving path.
#
# Defaults: 1 h in the browser, 7 d in a shared/CDN cache. The browser TTL is
# deliberately short because re-ingesting the relief COGs changes tile content
# at the same URLs, and browser caches cannot be purged; a CDN can, so s-maxage
# is free to be long. Override via TILE_CACHE_CONTROL (e.g. "no-cache" while
# actively iterating on the relief algorithm).
#
# /relief/packing is excluded: it carries the scale_factor/add_offset used to
# map metres <-> DN, so a stale copy silently mis-maps the colour ramp with no
# error anywhere. It is one small request per page load and is already cached
# in-process server-side, so there is nothing to gain and a silent-corruption
# mode to lose.
#
# cachecontrol_max_http_code=500 means 5xx responses get no header — important
# so a cold-start 503 is never cached in place of a tile.
app.add_middleware(
    CacheControlMiddleware,
    cachecontrol=os.environ.get(
        "TILE_CACHE_CONTROL", "public, max-age=3600, s-maxage=604800"
    ),
    cachecontrol_max_http_code=500,
    exclude_path={r"^/relief/packing$"},
)

app.include_router(mosaic.router, prefix="/mosaicjson")
add_exception_handlers(app, DEFAULT_STATUS_CODES)
add_exception_handlers(app, MOSAIC_STATUS_CODES)

# AWS Lambda entry point — Mangum translates Lambda events into ASGI requests.
# When running locally with Uvicorn, this line is harmlessly ignored.
handler = Mangum(app)


@app.get("/relief/packing", summary="Packing metadata for relief COGs")
def relief_packing(request: Request):
    """
    Returns the scale_factor and add_offset stamped into the relief COGs.
    Clients use these to convert physical units (metres) <-> raw DN:
      physical = raw * scale_factor + add_offset
      raw      = (physical - add_offset) / scale_factor
    """
    state = load_state()
    return JSONResponse({
        "scale_factor": state["scale_factor"],
        "add_offset":   state["add_offset"],
    })
