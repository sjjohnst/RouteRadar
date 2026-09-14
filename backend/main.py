"""app.

app/main.py

Serves COG mosaic tiles and elevation data from Cloudflare R2 via TiTiler.
The MosaicJSON is pre-built by ingestion/build_mosaic.py and fetched lazily
on the first request to each Lambda container (see state.py).
"""

import os
import logging
from contextlib import asynccontextmanager

# Must run before rasterio/boto3/GDAL are imported below — see r2_env.py.
from r2_env import configure_r2_environment
configure_r2_environment()

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
