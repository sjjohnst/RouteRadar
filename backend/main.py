"""app.

app/main.py

Serves COG mosaic tiles and elevation data from Cloudflare R2 via TiTiler.
The MosaicJSON is pre-built by ingestion/build_mosaic.py and fetched lazily
on the first request to each Lambda container (see state.py).
"""

import os
import logging

# Must run before rasterio/boto3/GDAL are imported below — see r2_env.py.
from r2_env import configure_r2_environment
configure_r2_environment()

from fastapi import FastAPI
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
# force=True: basicConfig() alone is a no-op and INFO logs from
# routeradar.titiler/state.py get silently dropped without this.
logging.basicConfig(level=logging.INFO, force=True)

# Lossless webp for relief tiles - better compression than png, while still being lossless
img_profiles["webp"] = {"quality": 100, "lossless": True}
assert img_profiles["webp"] == {"quality": 100, "lossless": True}, (
    "rio_tiler.profiles.img_profiles rejected the webp override — "
    "relief tiles would silently fall back to lossy webp"
)


app = FastAPI(
    title="RouteRadar TiTiler",
    description="Serves slope COG tiles from Cloudflare R2.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Cache-Control for tile responses.
# cachecontrol_max_http_code=204: only responses strictly below 204 (i.e. a
# normal 200 tile) get the header. Titiler returns 204 No Content, not 404,
# for a tile with no covering COG — caching that in the browser for an hour
# means re-ingesting new coverage doesn't show up there until the cache
# expires. 4xx/5xx are excluded for the same reason.
app.add_middleware(
    CacheControlMiddleware,
    cachecontrol=os.environ.get(
        "TILE_CACHE_CONTROL", "public, max-age=3600, s-maxage=604800"
    ),
    cachecontrol_max_http_code=204,
    exclude_path={r"^/relief/packing$"},
)

app.include_router(mosaic.router, prefix="/mosaicjson")
add_exception_handlers(app, DEFAULT_STATUS_CODES)
add_exception_handlers(app, MOSAIC_STATUS_CODES)

# AWS Lambda entry point — Mangum translates Lambda events into ASGI requests.
# When running locally with Uvicorn, this line is harmlessly ignored.
handler = Mangum(app)


@app.get("/relief/packing", summary="Packing metadata for relief COGs")
def relief_packing():
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
