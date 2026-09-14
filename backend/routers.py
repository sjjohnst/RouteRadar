"""routes.

app/routers.py

Exposes the mosaic tile endpoints for the frontend map application:
  GET /mosaicjson/tiles/{tileMatrixSetId}/{z}/{x}/{y}  — raster tile PNG/WebP
  GET /mosaicjson/{tileMatrixSetId}/tilejson.json      — TileJSON 3.0 metadata
  GET /mosaicjson/point/{lon},{lat}                    — packed value at a point

"""

from fastapi import Request
from titiler.mosaic.factory import MosaicTilerFactory
from cogeo_mosaic.backends.memory import MemoryBackend
from state import load_state

def _mosaic_path(request: Request) -> dict:
    """Return the MosaicJSON dict from the lazy-loaded in-process cache."""
    return load_state()["mosaic_dict"]

mosaic = MosaicTilerFactory(
    backend=MemoryBackend,
    path_dependency=_mosaic_path
)

# MosaicTilerFactory registers routes (/info, /*/assets, /*/map.html) that this
# app never uses and that leak the private R2 COG URIs behind each mosaic tile
# — drop them rather than exposing that surface just because the factory
# includes it by default. Only tiles/tilejson/point stay, matching README.md's
# documented API.
mosaic.router.routes = [
    route
    for route in mosaic.router.routes
    if "assets" not in route.path
    and "map.html" not in route.path
    and route.path not in ("/info", "/info.geojson")
]
