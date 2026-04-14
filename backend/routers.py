"""routes.

app/routers.py

Exposes two endpoints for the frontend map application:
  GET /mosaic/tiles/{z}/{x}/{y}    — raster tile PNG/WebP
  GET /mosaic/tilejson.json        — TileJSON 3.0 metadata

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
