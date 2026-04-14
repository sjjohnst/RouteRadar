"""state.py — lazy-loaded in-process cache for mosaic and packing metadata.

Extracted into its own module to break the circular import between main.py
(which imports routers) and routers.py (which needs _load_state).
"""

import json
import logging
import os

import boto3
from botocore.config import Config
import rasterio

logger = logging.getLogger("routeradar.titiler")

DEFAULT_SCALE_FACTOR = float(os.environ.get("COG_SCALE_FACTOR", "0.01"))
DEFAULT_ADD_OFFSET   = float(os.environ.get("COG_ADD_OFFSET",   "0.0"))
MOSAIC_KEY           = os.environ.get("MOSAIC_OUTPUT_KEY", "mosaic/relief.json")

_cache: dict = {}


def r2_endpoint() -> str:
    """Return the R2 S3 endpoint URL from whichever env var is set."""
    return os.environ.get("AWS_S3_ENDPOINT_URL") or os.environ["R2_S3_ENDPOINT"]


def load_state() -> dict:
    """Fetch MosaicJSON and packing metadata from R2; cache in-process.

    Called on the first request to the Lambda container. Subsequent calls
    within the same warm instance return the cached dict immediately.
    """
    if _cache:
        return _cache

    bucket       = os.environ["R2_BUCKET"]
    endpoint_url = r2_endpoint()

    # Fetch the pre-built MosaicJSON uploaded by ingestion/build_mosaic.py.
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("R2_REGION", "auto"),
        config=Config(signature_version="s3v4"),
    )
    logger.info("Fetching MosaicJSON from s3://%s/%s …", bucket, MOSAIC_KEY)
    response = s3.get_object(Bucket=bucket, Key=MOSAIC_KEY)
    mosaic_dict = json.loads(response["Body"].read())
    logger.info("MosaicJSON loaded — %d quadkeys", len(mosaic_dict.get("tiles", {})))

    # Read scale_factor / add_offset from a sample COG's dataset-level tags.
    scale_factor = DEFAULT_SCALE_FACTOR
    add_offset   = DEFAULT_ADD_OFFSET
    try:
        tiles: dict = mosaic_dict.get("tiles", {})
        sample_uri: str | None = next(
            (assets[0] for assets in tiles.values() if assets), None
        )
        if sample_uri:
            # GDAL S3 credentials are set as real OS env vars at startup (main.py).
            # rasterio ≥1.4 blocks AWS_* credential vars inside rasterio.Env,
            # so we open the COG directly — GDAL reads credentials from the process env.
            with rasterio.open(sample_uri) as src:
                tags = src.tags()
                scale_factor = float(tags.get("scale_factor", DEFAULT_SCALE_FACTOR))
                add_offset   = float(tags.get("add_offset",   DEFAULT_ADD_OFFSET))
            logger.info("Packing metadata: scale_factor=%s, add_offset=%s", scale_factor, add_offset)
    except Exception as exc:
        logger.warning("Could not read packing metadata from COG, using defaults: %s", exc)

    _cache["mosaic_dict"]  = mosaic_dict
    _cache["scale_factor"] = scale_factor
    _cache["add_offset"]   = add_offset
    return _cache
