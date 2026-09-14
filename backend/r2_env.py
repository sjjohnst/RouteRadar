"""r2_env.py — process environment setup for talking to Cloudflare R2.

Must run before rasterio/boto3/GDAL are first imported,as GDAL reads AWS_* 
from the process environment when its S3 driver initialises, and rasterio
>=1.4 refuses AWS_* credentials passed via rasterio.Env, so the process
environment is the only channel available.

None of this can move to the Dockerfile or Lambda config: Lambda reserves the
AWS_* names, which is the reason the R2_* indirection exists at all, and
AWS_SESSION_TOKEN is injected by the IAM role at invocation time, so it has to
be cleared from inside the process.
"""

import os
import sys

# R2 cannot be reached without any of these: GDAL needs the credentials to open
# a COG, and state.py needs the endpoint and bucket to fetch the MosaicJSON.
REQUIRED_VARS = (
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_S3_ENDPOINT",
    "R2_BUCKET",
)


def configure_r2_environment() -> None:
    """Validate the R2 config and map it onto the AWS_* vars GDAL/boto3 read.

    Raises RuntimeError if called too late to take effect, or if any required
    variable is missing — naming all of them, so a half-configured deployment
    fails here instead of on its first tile with a bare KeyError.
    """
    if "rasterio" in sys.modules or "boto3" in sys.modules:
        raise RuntimeError(
            "configure_r2_environment() ran after rasterio/boto3 were imported, "
            "so GDAL has already read the environment. Move the call above "
            "those imports — see this module's docstring."
        )

    missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required R2 environment variable(s): " + ", ".join(missing)
        )

    os.environ["AWS_ACCESS_KEY_ID"]     = os.environ["R2_ACCESS_KEY_ID"]
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ["R2_SECRET_ACCESS_KEY"]

    # R2 only accepts its own region slugs (auto, wnam, enam, …), not AWS region
    # names. Lambda injects AWS_REGION=ca-central-1; unset it entirely so
    # GDAL/boto3 don't send it to R2. state.py passes region_name="auto"
    # explicitly to its boto3 client, and GDAL uses the endpoint URL directly.
    os.environ.pop("AWS_REGION", None)
    os.environ.pop("AWS_DEFAULT_REGION", None)

    # R2 doesn't support STS session tokens, and Lambda's IAM role sets one.
    os.environ.pop("AWS_SESSION_TOKEN", None)

    # GDAL wants the endpoint hostname without a scheme.
    os.environ["AWS_S3_ENDPOINT"]     = os.environ["R2_S3_ENDPOINT"].replace("https://", "")
    os.environ["AWS_VIRTUAL_HOSTING"] = "NO"
    os.environ["AWS_HTTPS"]           = "YES"
