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
if "R2_ACCESS_KEY_ID" in os.environ:
    os.environ["AWS_ACCESS_KEY_ID"]     = os.environ["R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ["R2_SECRET_ACCESS_KEY"]
    os.environ["AWS_REGION"]            = os.environ.get("R2_REGION", "auto")

from cogeo_mosaic.backends.memory import MemoryBackend
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum
import rasterio

from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.mosaic.errors import MOSAIC_STATUS_CODES

from routers import mosaic
from state import load_state, r2_endpoint

logger = logging.getLogger("routeradar.titiler")
logging.basicConfig(level=logging.INFO)


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

app.include_router(mosaic.router, prefix="/mosaicjson")
add_exception_handlers(app, DEFAULT_STATUS_CODES)
add_exception_handlers(app, MOSAIC_STATUS_CODES)

# AWS Lambda entry point — Mangum translates Lambda events into ASGI requests.
# When running locally with Uvicorn, this line is harmlessly ignored.
handler = Mangum(app)


@app.get("/relief/packing", summary="Packing metadata for relief COGs")
async def relief_packing(request: Request):
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


@app.get("/relief/point", summary="Query relief elevation at a geographic point")
async def relief_point(
    request: Request,
    lng: float = Query(..., description="Longitude (WGS-84 decimal degrees)"),
    lat: float = Query(..., description="Latitude  (WGS-84 decimal degrees)"),
):
    """
    Returns the interpolated surface elevation (in metres) at the given
    longitude/latitude by reading the in-memory mosaic directly with rasterio.

    Response schema:
      { "lng": float, "lat": float, "elevation_m": float | null }
    """
    state        = load_state()
    mosaic_dict  = state["mosaic_dict"]
    scale_factor = state["scale_factor"]
    add_offset   = state["add_offset"]

    try:
        backend = MemoryBackend(mosaic_dict)
        assets = backend.get_assets(lng, lat)
        if not assets:
            return JSONResponse({"lng": lng, "lat": lat, "elevation_m": None})

        with rasterio.Env(
            AWS_S3_ENDPOINT=r2_endpoint().replace("https://", ""),
            AWS_VIRTUAL_HOSTING=False,
            AWS_ACCESS_KEY_ID=os.environ["R2_ACCESS_KEY_ID"],
            AWS_SECRET_ACCESS_KEY=os.environ["R2_SECRET_ACCESS_KEY"],
            AWS_SESSION_TOKEN="",          # suppress Lambda role STS token
        ):
            for asset in assets:
                try:
                    with rasterio.open(asset) as src:
                        vals = list(src.sample([(lng, lat)], indexes=1))
                        raw = float(vals[0][0])
                        if src.nodata is not None and raw == src.nodata:
                            continue
                        elevation_m = raw * scale_factor + add_offset
                        return JSONResponse({"lng": lng,
                                             "lat": lat,
                                             "elevation_m": round(elevation_m, 3)})
                except Exception:
                    continue

        return JSONResponse({"lng": lng, "lat": lat, "elevation_m": None})

    except Exception as exc:
        logger.error("Error querying relief point (%.5f, %.5f): %s", lng, lat, exc)
        return JSONResponse(
            {"detail": "Internal error querying relief point."},
            status_code=500,
        )
