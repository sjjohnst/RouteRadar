import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Tuple

import boto3
from botocore.client import Config
import rasterio
from rasterio.windows import Window
from dotenv import load_dotenv
import numpy as np
from pyproj import Transformer
from pystac_client import Client as StacClient
from shapely.geometry import shape, box
from tqdm import tqdm


class DTMIngestor:
    """
    Downloads DTM data from a STAC API over a given AOI, computes slope,
    and writes per-tile Cloud-Optimized GeoTIFFs (COGs) in EPSG:3857.

    Each COG covers (tile_size × tile_size) pixels at pixel_size m/px and
    is optimised for web-map serving: 256×256 internal blocks, ZSTD
    compression, a full overview pyramid, and an optional upload to R2.
    """

    BUFFER_PIXELS = 1  # 1-pixel border used during slope computation

    # Maximum rows to hold in RAM at once during relief/slope computation.
    # At 1 m/px, 2048 rows × 32768 cols × float32 ≈ 256 MB — well within WSL limits.
    # Increase for faster I/O on machines with more RAM; decrease to reduce peak usage.
    STRIP_HEIGHT = 2048

    def __init__(
        self,
        stac_api: str,
        geojson_path: str,
        output_dir: str,
        tile_size: int,
        pixel_size: int = 1,
        replace: bool = False,
        compute_slope: bool = True,
        compute_relief: bool = True,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.slope_dir = self.output_dir / "slope_tiles"
        self.relief_dir = self.output_dir / "relief_tiles"
        self.do_slope = compute_slope
        self.do_relief = compute_relief
        if self.do_slope:
            self.slope_dir.mkdir(exist_ok=True)
        if self.do_relief:
            self.relief_dir.mkdir(exist_ok=True)
        self.tile_size = tile_size  # pixels per tile edge
        self.pixel_size = pixel_size  # metres per pixel
        self.replace = replace
        self.r2_client = None

        self.logger = self._setup_logger()

        self.client = StacClient.open(stac_api)
        self.aoi_geom = self._load_aoi(geojson_path)
        self.mosaic_urls = self._fetch_mosaic_urls()

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("DTMIngestor")
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s")
        log_path = self.output_dir.parent / "dtm_ingestion.log"

        if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            fh = logging.FileHandler(log_path)
            fh.setFormatter(fmt)
            logger.addHandler(fh)

        if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            logger.addHandler(sh)

        return logger

    def _load_aoi(self, geojson_path: str):
        """Load AOI geometry from a GeoJSON file."""
        with open(geojson_path) as f:
            data = json.load(f)
        geom = data.get("geometry", data)
        return shape(geom)

    def _fetch_mosaic_urls(self) -> list[str]:
        """Query STAC and return /vsicurl/-prefixed DTM asset URLs."""
        search = self.client.search(
            collections=["hrdem-mosaic-1m"],
            bbox=self.aoi_geom.bounds,
            limit=10,
        )
        items = list(search.items())
        if not items:
            raise ValueError("No STAC items found for the given AOI.")

        self.logger.info("Found %d STAC item(s):", len(items))
        for item in items:
            self.logger.info("  - %s", item.id)

        urls = []
        for item in items:
            # Prefer the VRT sidecar over the raw COG:
            #   - VRT declares 512×512 blocks (vs implicit COG blocks), halving round-trips
            #   - VRT carries an explicit OverviewList so gdalwarp can pick the right
            #     overview level for the target resolution without extra HEAD requests
            #   - VRT is in the native EPSG:3979 projection — no extra metadata fetches
            asset_key = "dtm-vrt" if "dtm-vrt" in item.assets else "dtm"
            if asset_key == "dtm-vrt":
                self.logger.info("  Using VRT sidecar for %s", item.id)
            else:
                self.logger.warning("  No VRT asset found for %s, falling back to COG", item.id)
            urls.append(f"/vsicurl/{item.assets[asset_key].href}")
        return urls

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def setup_r2_client(
        self,
        r2_access_key: str,
        r2_secret_key: str,
        r2_endpoint_url: str,
        r2_bucket: str,
    ):
        """Configure the optional R2 upload target."""
        self.r2_bucket = r2_bucket
        self.r2_client = boto3.client(
            "s3",
            aws_access_key_id=r2_access_key,
            aws_secret_access_key=r2_secret_key,
            endpoint_url=r2_endpoint_url,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )

    def create_tiles(self):
        """Iterate over the AOI grid and process each intersecting tile."""
        projected_aoi = self._project_aoi()
        minx, miny, maxx, maxy = projected_aoi.bounds
        tile_size_m = self.tile_size * self.pixel_size

        cols = list(np.arange(minx, maxx, tile_size_m))
        rows = list(np.arange(miny, maxy, tile_size_m))
        self.logger.info(
            "Grid: %d×%d tiles (%dpx @ %dm/px) in EPSG:3857",
            len(cols), len(rows), self.tile_size, self.pixel_size,
        )

        bboxes = [
            [x, y, x + tile_size_m, y + tile_size_m]
            for x in cols
            for y in rows
        ]
        self.logger.info("Processing %d tiles intersecting the AOI...", len(bboxes))

        tile_id = 0
        for bbox in tqdm(bboxes, desc="Processing tiles"):
            if projected_aoi.intersects(box(*bbox)):
                self._process_tile(bbox, tile_id)
            tile_id += 1

    # ------------------------------------------------------------------
    # Per-tile pipeline
    # ------------------------------------------------------------------

    def _process_tile(self, bbox: list[float], tile_id: int):
        """Full pipeline for a single tile: extract - transform - upload."""
        slope_file  = self.slope_dir  / f"slope_tile_{tile_id}.tif"
        relief_file = self.relief_dir / f"relief_tile_{tile_id}.tif"

        already_done = (
            (not self.do_slope  or slope_file.exists()) and
            (not self.do_relief or relief_file.exists())
        )
        if already_done and not self.replace:
            self.logger.info("Tile %d already exists, skipping.", tile_id)
            return

        dtm_buf_file = self._download_dtm(bbox, tile_id)

        if self.do_slope:
            tmp_slope_file, slope_scale, slope_offset = self._compute_slope(dtm_buf_file, tile_id)
            self._write_cog(tmp_slope_file, slope_file, tile_id, scale=slope_scale, offset=slope_offset)
            self._cleanup(tmp_slope_file)
            if self.r2_client:
                self._upload_to_r2(slope_file, f"slope_tiles/slope_tile_{tile_id}.tif")

        if self.do_relief:
            tmp_relief_file, relief_scale, relief_offset = self._compute_relief(dtm_buf_file, tile_id)
            self._write_cog(tmp_relief_file, relief_file, tile_id, scale=relief_scale, offset=relief_offset)
            self._cleanup(tmp_relief_file)
            if self.r2_client:
                self._upload_to_r2(relief_file, f"relief_tiles/relief_tile_{tile_id}.tif")

        self._cleanup(dtm_buf_file)

    def _download_dtm(self, bbox: list[float], tile_id: int) -> Path:
        """
        Fetch a 1-pixel-buffered DTM tile from the remote mosaic via gdalwarp.
        Returns the path to the downloaded file.

        Performance notes
        -----------------
        The HRDEM mosaic is served as a COG over HTTPS.  gdalwarp reads it via
        GDAL's /vsicurl/ driver, which by default makes many small HTTP range
        requests — one per internal COG block touched during reprojection.  At
        typical WSL → internet latency (~20 ms RTT) this serialises to ~0.5 MB/s
        even on a fast connection.  The env vars below fix this:

        GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES
            Merges adjacent range requests into a single, larger HTTP request,
            dramatically reducing round-trips when reading sequential COG blocks.

        GDAL_HTTP_MULTIPLEX=YES  +  GDAL_HTTP_MAX_CONNECTIONS=8
            Sends up to 8 range requests in parallel over a single HTTP/2
            multiplexed connection, hiding per-request latency.

        GDAL_CACHEMAX (via --config inside gdalwarp)
            Raises GDAL's internal block cache from the default 5 % of RAM
            (~200 MB on most machines) to 1 GB so remote blocks fetched for
            overview resampling are reused rather than re-fetched.
        """
        minx, miny, maxx, maxy = bbox
        buf = self.BUFFER_PIXELS * self.pixel_size
        size = self.tile_size + 2 * self.BUFFER_PIXELS

        out_file = self.output_dir / f"dtm_tile_{tile_id}_buffered.tif"

        # Inherit the current environment and layer in the /vsicurl/ tuning.
        # These are set as subprocess env vars (not os.environ) so they only
        # affect this gdalwarp call and don't leak into the Python process.
        env = os.environ.copy()
        env.update({
            "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
            "GDAL_HTTP_MULTIPLEX":               "YES",
            "GDAL_HTTP_MAX_CONNECTIONS":         "8",
            "GDAL_DISABLE_READDIR_ON_OPEN":      "EMPTY_DIR",
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS":  ".tif,.vrt",
        })

        cmd = [
            "gdalwarp",
            "-q",
            "--config", "GDAL_CACHEMAX", "1024",
            "-t_srs", "EPSG:3857",
            "-multi",
            "-wo", "NUM_THREADS=ALL_CPUS",
            "-te", str(minx - buf), str(miny - buf), str(maxx + buf), str(maxy + buf),
            "-ts", str(size), str(size),
            "-of", "GTiff",
            "-co", "COMPRESS=DEFLATE",
            # Tiled layout enables efficient random-access strip reads during compute
            "-co", "TILED=YES",
            "-co", "BLOCKXSIZE=256",
            "-co", "BLOCKYSIZE=256",
            "-co", "NUM_THREADS=ALL_CPUS",
            *self.mosaic_urls,
            str(out_file),
        ]
        self.logger.info("Downloading DTM for tile %d...", tile_id)
        subprocess.run(cmd, check=True, env=env)
        return out_file

    def _compute_relief(self, buffered_path: Path, tile_id: int) -> tuple[Path, float, float]:
        """
        Compute local 2×2 relief (max - min) in horizontal strips to cap RAM usage.

        Peak RAM ≈ STRIP_HEIGHT × tile_width × 6 arrays × 4 bytes
        e.g. 2048 × 32768 × 6 × 4 ≈ 1.5 GB — safe for WSL.
        """
        SCALE  = 0.01   # 1 cm precision
        OFFSET = 0.0

        tmp = buffered_path.parent / f"relief_tmp_{tile_id}.tif"

        with rasterio.open(buffered_path) as src:
            src_h     = src.height
            src_w     = src.width
            nodata    = src.nodata
            transform = src.transform
            crs       = src.crs
            res       = self.pixel_size

            # The buffered source is (tile_size + 2*buf) × (tile_size + 2*buf).
            # The 2×2 kernel at output pixel [r, c] reads source pixels
            # [r, c], [r, c+1], [r+1, c], [r+1, c+1].  Starting the output
            # grid at source row/col `buf` means the first kernel window is
            # fully inside the original (unbuffered) tile, and the last window
            # at source row (src_h - 2) stays inside the buffer edge.
            # Result: exactly tile_size × tile_size output pixels.
            buf   = 1  # == BUFFER_PIXELS; local alias for clarity
            out_h = src_h - 2 * buf  # == tile_size  (e.g. 32768)
            out_w = src_w - 2 * buf

            # Origin shifts by buf pixels (top-left corner of the first kernel
            # window sits at the top-left corner of the unbuffered tile).
            new_origin_x = transform.c + buf * res
            new_origin_y = transform.f - buf * res
            new_transform = rasterio.transform.from_origin(new_origin_x, new_origin_y, res, res)

            out_profile = {
                "driver":    "GTiff",
                "height":    out_h,
                "width":     out_w,
                "count":     1,
                "dtype":     "uint16",
                "crs":       crs,
                "transform": new_transform,
            }

            with rasterio.open(tmp, "w", **out_profile) as dst:
                strip = self.STRIP_HEIGHT

                # We need one extra source row below each strip to complete the
                # 2×2 kernel at the strip boundary, so we read (rows_to_write + 1)
                # source rows but only write rows_to_write output rows.
                # Source row index = output row index + buf (skip the top buffer).
                for row_start in range(0, out_h, strip):
                    rows_to_write = min(strip, out_h - row_start)
                    src_row_start = row_start + buf
                    src_row_end   = src_row_start + rows_to_write + 1  # +1 for bottom kernel edge

                    win = Window(0, src_row_start, src_w, src_row_end - src_row_start)
                    arr = src.read(1, window=win).astype(np.float32)

                    if nodata is not None:
                        valid_mask = ~np.isclose(arr, nodata)
                    else:
                        valid_mask = np.isfinite(arr)

                    sentinel = float(np.nanmax(arr[valid_mask])) if valid_mask.any() else 0.0
                    arr_safe = np.where(valid_mask, arr, sentinel)

                    # 2×2 kernel over the strip (output rows = arr_rows - 1)
                    local_max = np.maximum(
                        np.maximum(arr_safe[:-1, :-1], arr_safe[:-1, 1:]),
                        np.maximum(arr_safe[1:,  :-1], arr_safe[1:,  1:]),
                    )
                    local_min = np.minimum(
                        np.minimum(arr_safe[:-1, :-1], arr_safe[:-1, 1:]),
                        np.minimum(arr_safe[1:,  :-1], arr_safe[1:,  1:]),
                    )
                    relief = local_max - local_min

                    corner_valid = (
                        valid_mask[:-1, :-1] & valid_mask[:-1, 1:] &
                        valid_mask[1:,  :-1] & valid_mask[1:,  1:]
                    )
                    relief = np.where(corner_valid, relief, 0.0)

                    # Trim to the actual output columns, skipping the left buffer column.
                    packed = np.round(relief[:rows_to_write, buf:buf + out_w] / SCALE).astype(np.uint16)

                    out_win = Window(0, row_start, out_w, rows_to_write)
                    dst.write(packed, 1, window=out_win)

        return tmp, SCALE, OFFSET

    def _compute_slope(self, dtm_file: Path, tile_id: int) -> Tuple[Path, float, float]:
        """
        Compute slope (degrees) from the buffered DTM in horizontal strips,
        crop the 1-pixel border, and write an intermediate GeoTIFF.

        Each strip reads (STRIP_HEIGHT + 2) source rows so that np.gradient
        has valid neighbours at both edges; only the interior rows are written.
        """
        SCALE  = 0.1   # 0.1° precision
        OFFSET = 0.0

        tmp_file = self.output_dir / f"slope_tile_{tile_id}_tmp.tif"

        with rasterio.open(dtm_file) as src:
            src_h     = src.height
            src_w     = src.width
            b         = self.BUFFER_PIXELS
            out_h     = src_h - 2 * b
            out_w     = src_w - 2 * b
            res       = abs(float(src.res[0]))
            transform = src.transform
            crs       = src.crs

            # Crop the buffer border from the transform origin
            new_transform = rasterio.transform.from_origin(
                transform.c + b * res,
                transform.f - b * res,
                res, res,
            )

            out_profile = {
                "driver":    "GTiff",
                "height":    out_h,
                "width":     out_w,
                "count":     1,
                "dtype":     "uint16",
                "crs":       crs,
                "transform": new_transform,
            }

            with rasterio.open(tmp_file, "w", **out_profile) as dst:
                strip = self.STRIP_HEIGHT

                for out_row in range(0, out_h, strip):
                    rows_to_write = min(strip, out_h - out_row)

                    # Source rows: output row `out_row` maps to source row `out_row + b`.
                    # Read one guard row above and below so np.gradient has valid neighbours.
                    src_start = max(out_row + b - 1, 0)
                    src_end   = min(out_row + b + rows_to_write + 1, src_h)

                    win = Window(0, src_start, src_w, src_end - src_start)
                    arr = src.read(1, window=win).astype(np.float64)

                    dz_dx, dz_dy = np.gradient(arr, res, res)
                    slope_full   = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))

                    # Extract only the rows corresponding to out_row..out_row+rows_to_write,
                    # accounting for the guard row above and the buffer offset.
                    inner_start = (out_row + b) - src_start
                    inner_end   = inner_start + rows_to_write

                    slope_strip = slope_full[inner_start:inner_end, b:b + out_w]

                    # Pack slope into uint16: unpacked = packed * SCALE + OFFSET
                    # scale_factor=0.1, add_offset=0.0 → 0.1° precision, range 0–6553.5°
                    packed = np.clip(
                        np.round((slope_strip - OFFSET) / SCALE), 0, np.iinfo(np.uint16).max
                    ).astype(np.uint16)

                    out_win = Window(0, out_row, out_w, rows_to_write)
                    dst.write(packed, 1, window=out_win)

        return tmp_file, SCALE, OFFSET

    def _write_cog(
        self, src: Path, dst: Path, tile_id: int,
        scale: float | None = None, offset: float | None = None,
    ):
        """
        Convert an intermediate GeoTIFF to a web-optimised COG via gdal_translate:
          - 512×512 blocks  (matches web-map tile size)
          - ZSTD compression with PREDICTOR=2
          - Full AUTO overview pyramid with AVERAGE resampling
          - Optional scale_factor / add_offset stamped as band metadata tags
            so that rasterio / GDAL readers can auto-unpack packed integers.
        """
        cmd = [
            "gdal_translate",
            "-of", "COG",
            "-co", "BLOCKSIZE=512",
            "-co", "COMPRESS=ZSTD",
            "-co", "LEVEL=9",
            "-co", "PREDICTOR=2",
            "-co", "OVERVIEWS=AUTO",
            "-co", "OVERVIEW_RESAMPLING=AVERAGE",
            "-co", "NUM_THREADS=ALL_CPUS",
        ]
        if scale is not None:
            cmd += ["-mo", f"scale_factor={scale}"]
        if offset is not None:
            cmd += ["-mo", f"add_offset={offset}"]
        cmd += [
            str(src),
            str(dst),
        ]
        self.logger.info("Writing COG for tile %d...", tile_id)
        subprocess.run(cmd, check=True)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _project_aoi(self):
        """Reproject the AOI polygon from EPSG:4326 to EPSG:3857."""
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        coords = [transformer.transform(lon, lat) for lon, lat in self.aoi_geom.exterior.coords]
        return shape({"type": "Polygon", "coordinates": [coords]})

    def _cleanup(self, *paths: Path):
        """Remove temporary files, logging any failures."""
        for path in paths:
            try:
                os.remove(path)
            except Exception as e:
                self.logger.warning("Could not remove %s: %s", path, e)

    def _upload_to_r2(self, local_path: Path, remote_key: str):
        """Upload a local file to the configured R2 bucket."""
        self.logger.info("Uploading %s → s3://%s/%s", local_path, self.r2_bucket, remote_key)
        self.r2_client.upload_file(str(local_path), self.r2_bucket, remote_key)

    def upload_tiles(self):
        """Upload all already-computed COG tiles to R2 without reprocessing."""
        if not self.r2_client:
            raise RuntimeError("R2 client not configured — call setup_r2_client() first.")

        dirs = [
            (self.slope_dir,  "slope_tiles"),
            (self.relief_dir, "relief_tiles"),
        ]
        for local_dir, remote_prefix in dirs:
            if not local_dir.exists():
                self.logger.info("Skipping %s — directory does not exist.", local_dir)
                continue
            tiles = sorted(local_dir.glob("*.tif"))
            if not tiles:
                self.logger.info("Skipping %s — no .tif files found.", local_dir)
                continue
            self.logger.info("Uploading %d tile(s) from %s...", len(tiles), local_dir)
            for tile in tqdm(tiles, desc=f"Uploading {remote_prefix}"):
                self._upload_to_r2(tile, f"{remote_prefix}/{tile.name}")


if __name__ == "__main__":
    load_dotenv()

    dtm_ingestor = DTMIngestor(
        stac_api="https://datacube.services.geo.ca/stac/api/",
        geojson_path="./data/aoi/massive_laurentides.geojson",
        output_dir="./data/tiles/",
        tile_size=2**15,  # 32768 px → ~32 km tiles at 1 m/px
        compute_slope=False,
        compute_relief=True,
    )
    dtm_ingestor.setup_r2_client(
        os.getenv("R2_ACCESS_KEY_ID"),
        os.getenv("R2_SECRET_ACCESS_KEY"),
        os.getenv("R2_S3_ENDPOINT"),
        os.getenv("R2_BUCKET"),
    )
    dtm_ingestor.upload_tiles()
