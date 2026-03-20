"""routes.

app/routers.py

Exposes two endpoints for the frontend map application:
  GET /mosaic/tiles/{z}/{x}/{y}    — raster tile PNG/WebP
  GET /mosaic/tilejson.json        — TileJSON 3.0 metadata

"""

from fastapi import Request
from titiler.mosaic.factory import MosaicTilerFactory
from cogeo_mosaic.backends.memory import MemoryBackend

def _mosaic_path(request: Request) -> dict:
    """Return the MosaicJSON dict from app state.

    MemoryBackend expects a dict as its input, not a URL string.
    """
    return request.app.state.mosaic_dict

mosaic = MosaicTilerFactory(
    backend=MemoryBackend,
    path_dependency=_mosaic_path
)
