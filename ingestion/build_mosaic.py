"""build_mosaic.py

Scans a prefix in Cloudflare R2 for Cloud-Optimized GeoTIFFs, builds a
MosaicJSON from them, and uploads the result back to R2 as a JSON file.

Run this script after ingestion whenever new COGs are added to R2.  The
Lambda backend will then fetch this pre-built file at cold-start instead
of rebuilding it from scratch (which would time out API Gateway).

Usage:
    python build_mosaic.py [--prefix relief_tiles/] [--output mosaic/relief.json]

All credentials are read from environment variables (or a .env file):
    R2_ACCESS_KEY_ID      — R2 access key
    R2_SECRET_ACCESS_KEY  — R2 secret key
    R2_S3_ENDPOINT        — e.g. https://<account>.r2.cloudflarestorage.com
    R2_BUCKET             — bucket name

Optional env vars (with defaults matching the Lambda backend):
    COG_PREFIX            — R2 prefix to scan  (default: relief_tiles/)
    COG_MINZOOM           — mosaic minzoom      (default: 7)
    COG_MAXZOOM           — mosaic maxzoom      (default: 18)
    MOSAIC_OUTPUT_KEY     — R2 key to upload to (default: mosaic/relief.json)
"""

import argparse
import json
import logging
import os

import boto3
from botocore.client import Config
from cogeo_mosaic.mosaic import MosaicJSON
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s][%(levelname)s] %(message)s",
)
logger = logging.getLogger("build_mosaic")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_r2_client(endpoint_url: str):
    return boto3.client(
        "s3",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        endpoint_url=endpoint_url,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def list_cog_uris(client, bucket: str, prefix: str) -> list[str]:
    """Return s3://<bucket>/<key> URIs for every .tif under *prefix*."""
    paginator = client.get_paginator("list_objects_v2")
    uris: list[str] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key: str = obj["Key"]
            if key.lower().endswith((".tif", ".tiff")):
                uris.append(f"s3://{bucket}/{key}")
    logger.info("Found %d COG(s) under s3://%s/%s", len(uris), bucket, prefix)
    return uris


def build_mosaic_dict(uris: list[str], minzoom: int, maxzoom: int) -> dict:
    """Build and return a MosaicJSON dict from a list of COG URIs."""
    logger.info("Building MosaicJSON (zoom %d–%d) from %d COGs …", minzoom, maxzoom, len(uris))

    mosaic = MosaicJSON.from_urls(
        uris,
        minzoom=minzoom,
        maxzoom=maxzoom,
    )
    logger.info(
        "MosaicJSON built — zoom %d–%d, %d quadkeys",
        mosaic.minzoom,
        mosaic.maxzoom,
        len(mosaic.tiles),
    )
    return mosaic.model_dump()


def upload_mosaic(client, bucket: str, key: str, mosaic_dict: dict) -> None:
    """Serialise *mosaic_dict* to JSON and upload it to R2."""
    body = json.dumps(mosaic_dict).encode("utf-8")
    logger.info(
        "Uploading MosaicJSON (%d bytes) → s3://%s/%s …",
        len(body), bucket, key,
    )
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )
    logger.info("Upload complete.")


def _inject_aws_env() -> None:
    """Force AWS_* env vars to R2 values so GDAL's S3 driver hits R2, not AWS.

    We forcibly overwrite (not setdefault) because the shell environment may
    already have AWS_REGION / AWS_ACCESS_KEY_ID etc. pointing at real AWS,
    which would cause GDAL to ignore the R2 endpoint and fail silently.
    """
    endpoint = os.environ["R2_S3_ENDPOINT"]
    # GDAL expects the hostname only, without the scheme.
    gdal_endpoint = endpoint.replace("https://", "").replace("http://", "")

    os.environ["AWS_ACCESS_KEY_ID"]     = os.environ["R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ["R2_SECRET_ACCESS_KEY"]
    os.environ["AWS_S3_ENDPOINT"]       = gdal_endpoint
    os.environ["AWS_DEFAULT_REGION"]    = "auto"
    os.environ["AWS_REGION"]            = "auto"
    os.environ["AWS_VIRTUAL_HOSTING"]   = "FALSE"
    os.environ["AWS_HTTPS"]             = "TRUE"


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build and upload a MosaicJSON from R2 COGs.")
    parser.add_argument(
        "--prefix",
        default=os.environ.get("COG_PREFIX", "relief_tiles/"),
        help="R2 key prefix to scan for COGs (default: relief_tiles/)",
    )
    parser.add_argument(
        "--output",
        default=os.environ.get("MOSAIC_OUTPUT_KEY", "mosaic/relief.json"),
        help="R2 key to write the MosaicJSON to (default: mosaic/relief.json)",
    )
    parser.add_argument(
        "--minzoom",
        type=int,
        default=int(os.environ.get("COG_MINZOOM", "7")),
        help="Mosaic minzoom (default: 7)",
    )
    parser.add_argument(
        "--maxzoom",
        type=int,
        default=int(os.environ.get("COG_MAXZOOM", "18")),
        help="Mosaic maxzoom (default: 18)",
    )
    args = parser.parse_args()

    endpoint_url = os.environ["R2_S3_ENDPOINT"]
    bucket       = os.environ["R2_BUCKET"]

    # Inject R2 credentials into AWS_* env vars before any GDAL/boto3 calls.
    _inject_aws_env()

    client = _make_r2_client(endpoint_url)

    uris = list_cog_uris(client, bucket, args.prefix)
    if not uris:
        raise SystemExit(
            f"No COGs found under s3://{bucket}/{args.prefix} — "
            "check R2_BUCKET and --prefix."
        )

    mosaic_dict = build_mosaic_dict(uris, args.minzoom, args.maxzoom)
    upload_mosaic(client, bucket, args.output, mosaic_dict)


if __name__ == "__main__":
    main()
