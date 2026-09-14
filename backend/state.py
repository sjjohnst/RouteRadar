"""state.py — lazy-loaded in-process cache for mosaic and packing metadata.

Extracted into its own module to break the circular import between main.py
(which imports routers) and routers.py (which needs load_state).
"""

import json
import logging
import os

import boto3
from botocore.config import Config

logger = logging.getLogger("routeradar.titiler")

DEFAULT_SCALE_FACTOR = float(os.environ.get("COG_SCALE_FACTOR", "0.01"))
DEFAULT_ADD_OFFSET   = float(os.environ.get("COG_ADD_OFFSET",   "0.0"))
MOSAIC_KEY           = os.environ.get("MOSAIC_OUTPUT_KEY", "mosaic/relief.json")

_cache: dict = {}


def r2_endpoint() -> str:
    """Return the R2 S3 endpoint URL, scheme included, as boto3 wants it.

    r2_env.configure_r2_environment() has already validated that this is set,
    and derives GDAL's scheme-less AWS_S3_ENDPOINT from the same value.
    """
    return os.environ["R2_S3_ENDPOINT"]


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

    # Packing constants are stamped into the MosaicJSON by build_mosaic.py, so
    # they cost nothing here — no COG is opened on the tile path. Mosaics built
    # before that change lack the keys; fall back to the env defaults and say so
    # loudly, because a wrong scale silently mis-maps the colour ramp instead of
    # raising anywhere.
    scale_factor = mosaic_dict.get("scale_factor")
    add_offset   = mosaic_dict.get("add_offset")
    if scale_factor is None or add_offset is None:
        logger.warning(
            "MosaicJSON carries no packing metadata — falling back to "
            "scale_factor=%s, add_offset=%s. Rebuild the mosaic with "
            "ingestion/build_mosaic.py to stamp the real values.",
            DEFAULT_SCALE_FACTOR, DEFAULT_ADD_OFFSET,
        )
        scale_factor = DEFAULT_SCALE_FACTOR
        add_offset   = DEFAULT_ADD_OFFSET
    else:
        logger.info(
            "Packing metadata: scale_factor=%s, add_offset=%s",
            scale_factor, add_offset,
        )

    _cache["mosaic_dict"]  = mosaic_dict
    _cache["scale_factor"] = scale_factor
    _cache["add_offset"]   = add_offset
    return _cache
