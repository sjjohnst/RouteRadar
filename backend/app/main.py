from fastapi import FastAPI
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import rioxarray as rxr
import numpy as np
from io import BytesIO
from PIL import Image
import matplotlib.pyplot as plt
import os

# path to DTM relative to repo root (robust resolution)
from pathlib import Path

# Find repository root by searching upward for a `data` directory (more robust than fixed parents)
this_file = Path(__file__).resolve()
search_dir = this_file.parent
repo_root = None
for parent in [search_dir] + list(search_dir.parents):
    if (parent / 'data').exists():
        repo_root = parent
        break
if repo_root is None:
    # fallback to two levels up
    repo_root = this_file.parents[2]

DTM_PATH = repo_root / "data" / "dtm" / "morin_heights_dtm_slope.tif"
REPROJECT_SHAPE = (800, 800)  # pixels for web overlay

app = FastAPI()

static_dir = os.path.join(os.path.dirname(__file__), "static")
# Mount static under /static so API routes are not shadowed by the static files handler
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def root_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return Response(content="Index not found", status_code=404)

# cached values filled at startup
_cached = {"png_bytes": None, "bounds": None, "center": None, 'error': None}


@app.on_event("startup")
def prepare_dtm_overlay():
    # load DTM, reproject to EPSG:4326 and render an RGBA PNG into memory
    try:
        print(f"Preparing DTM overlay. Looking for DTM at: {DTM_PATH}")
        if not DTM_PATH.exists():
            msg = f"DTM not found at: {DTM_PATH}"
            print(msg)
            _cached['error'] = msg
            return
        dtm = rxr.open_rasterio(str(DTM_PATH), chunks={"x": 1024, "y": 1024}).squeeze()

        dtm = dtm.where(dtm != dtm.rio.nodata, np.nan)
        dtm_ll = dtm.rio.reproject("EPSG:4326", shape=REPROJECT_SHAPE)
        arr = np.squeeze(dtm_ll.values)  # (H, W)
        # normalize to 0..1 and map to terrain colormap
        arr_mask = np.isnan(arr)
        vmin = np.nanmin(arr)
        vmax = np.nanmax(arr)
        if np.isfinite(vmin) and np.isfinite(vmax) and vmax > vmin:
            norm = (arr - vmin) / (vmax - vmin)
        else:
            norm = np.zeros_like(arr)
        norm = np.clip(norm, 0.0, 1.0)

        cmap = plt.get_cmap("terrain")
        rgba = cmap(norm)  # floats 0..1 (H,W,4)
        rgba[..., 3] = np.where(arr_mask, 0.0, rgba[..., 3])  # transparent where nodata
        rgba_uint8 = (rgba * 255).astype("uint8")

        # save to PNG bytes
        img = Image.fromarray(rgba_uint8)
        bio = BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)

        left, bottom, right, top = dtm_ll.rio.bounds()
        center_lat = (bottom + top) / 2.0
        center_lon = (left + right) / 2.0

        _cached["png_bytes"] = bio.read()
        _cached["bounds"] = [bottom, left, top, right]  # Leaflet expects [[south, west], [north, east]]
        _cached["center"] = [center_lat, center_lon]
        print(f"DTM overlay prepared. bounds: { _cached['bounds'] }")
    except Exception as exc:
        msg = f"Error preparing DTM overlay: {exc}"
        print(msg)
        _cached['error'] = msg
        return


@app.get("/dtm_info")
def dtm_info():
    if _cached.get('error'):
        return JSONResponse({"error": _cached.get('error')}, status_code=500)
    if _cached.get("bounds") is None:
        return JSONResponse({"error": "DTM not prepared yet"}, status_code=503)
    return {
        "bounds": [[_cached["bounds"][0], _cached["bounds"][1]], [_cached["bounds"][2], _cached["bounds"][3]]],
        "center": _cached["center"],
        "image_url": "/dtm.png",
    }


@app.get("/dtm.png")
def dtm_png():
    if _cached["png_bytes"] is None:
        return Response(status_code=404)
    return Response(content=_cached["png_bytes"], media_type="image/png")


@app.get("/dtm_debug")
def dtm_debug():
    """Return backend DTM path information for debugging."""
    try:
        exists = DTM_PATH.exists()
        size = DTM_PATH.stat().st_size if exists else None
    except Exception:
        exists = False
        size = None
    return {"dtm_path": str(DTM_PATH), "exists": exists, "size_bytes": size, "cached_error": _cached.get('error')}
