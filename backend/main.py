"""app.

app/main.py

On startup the app:
  1. Lists every *.tif object under the relief_tiles/ prefix in the
     configured R2 bucket.
  2. Builds a MosaicJSON from those S3 URIs using cogeo-mosaic.
  3. Stores the resulting dict in app.state.mosaic_dict so the router
     can instantiate R2MosaicBackend on each request.

The mosaic is always rebuilt from scratch at startup, so adding new COGs
to R2 only requires a service restart.
"""

import os
import logging
from contextlib import asynccontextmanager

import boto3
from botocore.config import Config
from cogeo_mosaic.mosaic import MosaicJSON
from cogeo_mosaic.backends.memory import MemoryBackend
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import rasterio

from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.mosaic.errors import MOSAIC_STATUS_CODES

from routers import mosaic

logger = logging.getLogger("routeradar.titiler")
logging.basicConfig(level=logging.INFO)

COG_MINZOOM = int(os.environ.get("COG_MINZOOM", "7"))
COG_MAXZOOM = int(os.environ.get("COG_MAXZOOM", "18"))
COG_PREFIX  = os.environ.get("COG_PREFIX", "relief_tiles/")
# Fallback packing constants — overridden at startup from actual COG metadata
DEFAULT_SCALE_FACTOR = float(os.environ.get("COG_SCALE_FACTOR", "0.01"))
DEFAULT_ADD_OFFSET   = float(os.environ.get("COG_ADD_OFFSET",   "0.0"))


def _list_cog_s3_uris(bucket: str, prefix: str, endpoint_url: str) -> list[str]:
    """Return a list of s3://<bucket>/<key> URIs for every .tif under prefix."""
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        config=Config(signature_version="s3v4"),
    )
    paginator = s3.get_paginator("list_objects_v2")
    uris: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key: str = obj["Key"]
            if key.lower().endswith(".tif") or key.lower().endswith(".tiff"):
                uris.append(f"s3://{bucket}/{key}")
    return uris


def _build_mosaic(uris: list[str]) -> dict:
    """Build and return a MosaicJSON dict from a list of COG S3 URIs."""
    logger.info("Building MosaicJSON from %d COGs …", len(uris))
    mosaic = MosaicJSON.from_urls(
        uris,
        minzoom=COG_MINZOOM,
        maxzoom=COG_MAXZOOM,
    )
    logger.info(
        "MosaicJSON built — zoom %d–%d, %d quadkeys",
        mosaic.minzoom,
        mosaic.maxzoom,
        len(mosaic.tiles),
    )
    return mosaic.dict()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the mosaic on startup; clean up on shutdown."""
    bucket       = os.environ["R2_BUCKET"]
    endpoint_url = os.environ["AWS_S3_ENDPOINT_URL"]

    logger.info("Listing COGs in s3://%s/%s …", bucket, COG_PREFIX)
    uris = _list_cog_s3_uris(bucket, COG_PREFIX, endpoint_url)
    if not uris:
        raise RuntimeError(
            f"No COG files found in s3://{bucket}/{COG_PREFIX} — "
            "check R2_BUCKET and COG_PREFIX."
        )
    logger.info("Found %d COG(s).", len(uris))

    app.state.mosaic_dict = _build_mosaic(uris)

    # Read scale_factor / add_offset from the first COG's dataset-level tags.
    # These are stamped by gdal_translate -mo during ingestion.
    scale_factor = DEFAULT_SCALE_FACTOR
    add_offset   = DEFAULT_ADD_OFFSET
    try:
        with rasterio.Env(
            AWS_S3_ENDPOINT=os.environ["AWS_S3_ENDPOINT_URL"].replace("https://", ""),
            AWS_VIRTUAL_HOSTING=False,
        ):
            with rasterio.open(uris[0]) as src:
                tags = src.tags()
                scale_factor = float(tags.get("scale_factor", DEFAULT_SCALE_FACTOR))
                add_offset   = float(tags.get("add_offset",   DEFAULT_ADD_OFFSET))
        logger.info("Packing metadata: scale_factor=%s, add_offset=%s", scale_factor, add_offset)
    except Exception as exc:
        logger.warning("Could not read packing metadata from COG, using defaults: %s", exc)

    app.state.scale_factor = scale_factor
    app.state.add_offset   = add_offset

    yield  # application runs here

    app.state.mosaic_dict  = None
    app.state.scale_factor = None
    app.state.add_offset   = None

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


@app.get("/relief/packing", summary="Packing metadata for relief COGs")
async def relief_packing(request: Request):
    """
    Returns the scale_factor and add_offset stamped into the relief COGs.
    Clients use these to convert physical units (metres) ↔ raw DN:
      physical = raw * scale_factor + add_offset
      raw      = (physical - add_offset) / scale_factor
    """
    return JSONResponse({
        "scale_factor": request.app.state.scale_factor,
        "add_offset":   request.app.state.add_offset,
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
    mosaic_dict = request.app.state.mosaic_dict
    scale_factor = request.app.state.scale_factor
    add_offset   = request.app.state.add_offset

    try:
        backend = MemoryBackend(mosaic_dict)
        # get_assets returns a list of asset paths that cover the point
        assets = backend.get_assets(lng, lat)
        if not assets:
            return JSONResponse({"lng": lng, "lat": lat, "elevation_m": None})

        # Try each asset in priority order; return the first valid pixel
        with rasterio.Env(
            AWS_S3_ENDPOINT=os.environ.get("AWS_S3_ENDPOINT_URL", "").replace("https://", ""),
            AWS_VIRTUAL_HOSTING=False,
        ):
            for asset in assets:
                try:
                    with rasterio.open(asset) as src:
                        # Sample returns an iterable of tuples, one per point
                        vals = list(src.sample([(lng, lat)], indexes=1))
                        raw = float(vals[0][0])
                        # nodata guard — rasterio returns nodata as the raw value
                        if src.nodata is not None and raw == src.nodata:
                            continue
                        elevation_m = raw * scale_factor + add_offset
                        return JSONResponse({"lng": lng, "lat": lat, "elevation_m": round(elevation_m, 3)})
                except Exception:
                    continue

        return JSONResponse({"lng": lng, "lat": lat, "elevation_m": None})

    except Exception as exc:
        logger.error("Error querying relief point (%.5f, %.5f): %s", lng, lat, exc)
        return JSONResponse(
            {"detail": "Internal error querying relief point."},
            status_code=500,
        )
