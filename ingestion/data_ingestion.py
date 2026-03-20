import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Tuple

import boto3
from botocore.client import Config
import rasterio
from dotenv import load_dotenv
import numpy as np
from pyproj import Transformer
from pystac_client import Client as StacClient
import rioxarray as rxr
from shapely.geometry import shape, box
from tqdm import tqdm
import xarray as xr


class DTMIngestor:
    """
    Downloads DTM data from a STAC API over a given AOI, computes slope,
    and writes per-tile Cloud-Optimized GeoTIFFs (COGs) in EPSG:3857.

    Each COG covers (tile_size × tile_size) pixels at pixel_size m/px and
    is optimised for web-map serving: 256×256 internal blocks, ZSTD
    compression, a full overview pyramid, and an optional upload to R2.
    """

    BUFFER_PIXELS = 1  # 1-pixel border used during slope computation

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

        return [f"/vsicurl/{item.assets['dtm'].href}" for item in items]

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
        """
        minx, miny, maxx, maxy = bbox
        buf = self.BUFFER_PIXELS * self.pixel_size
        size = self.tile_size + 2 * self.BUFFER_PIXELS

        out_file = self.output_dir / f"dtm_tile_{tile_id}_buffered.tif"
        cmd = [
            "gdalwarp",
            "-q",
            "-t_srs", "EPSG:3857",
            "-multi",
            "-wo", "NUM_THREADS=ALL_CPUS",
            "-te", str(minx - buf), str(miny - buf), str(maxx + buf), str(maxy + buf),
            "-ts", str(size), str(size),
            "-of", "GTiff",
            "-co", "COMPRESS=DEFLATE",
            "-co", "NUM_THREADS=ALL_CPUS",
            *self.mosaic_urls,
            str(out_file),
        ]
        self.logger.info("Downloading DTM for tile %d...", tile_id)
        subprocess.run(cmd, check=True)
        return out_file

    def _compute_relief(self, buffered_path: Path, tile_id: int) -> tuple[Path, float, float]:
        SCALE  = 0.01   # 1 cm precision
        OFFSET = 0.0

        da      = rxr.open_rasterio(buffered_path, masked=True).squeeze()
        arr     = da.values.astype(np.float32)          # (rows, cols)
        nodata  = da.rio.nodata or da.rio.encoded_nodata

        # Replace nodata with a high sentinel so it never drives the minimum down
        if nodata is not None:
            valid_mask = ~np.isclose(arr, nodata)
        else:
            valid_mask = np.isfinite(arr)
        sentinel = np.nanmax(arr[valid_mask]) if valid_mask.any() else 0.0
        arr_safe = np.where(valid_mask, arr, sentinel)

        # 2×2 kernel — result lives at pixel-corner intersections
        # shape: (rows-1, cols-1)
        local_max = np.maximum(
            np.maximum(arr_safe[:-1, :-1], arr_safe[:-1, 1:]),
            np.maximum(arr_safe[1:,  :-1], arr_safe[1:,  1:]),
        )
        local_min = np.minimum(
            np.minimum(arr_safe[:-1, :-1], arr_safe[:-1, 1:]),
            np.minimum(arr_safe[1:,  :-1], arr_safe[1:,  1:]),
        )
        relief = local_max - local_min

        # Zero out windows where any of the 4 pixels was nodata
        corner_valid = (
            valid_mask[:-1, :-1] & valid_mask[:-1, 1:] &
            valid_mask[1:,  :-1] & valid_mask[1:,  1:]
        )
        relief = np.where(corner_valid, relief, 0.0)

        packed = np.round(relief / SCALE).astype(np.uint16)

        # Shift origin by +0.5 px so coordinates sit on pixel-corner intersections
        res       = self.pixel_size
        transform = da.rio.transform()
        new_origin_x = transform.c + 0.5 * res
        new_origin_y = transform.f - 0.5 * res          # y increases downward in transform
        new_transform = rasterio.transform.from_origin(
            new_origin_x, new_origin_y,
            res, res,
        )

        tmp = buffered_path.parent / f"relief_tmp_{tile_id}.tif"
        with rasterio.open(
            tmp, "w",
            driver="GTiff",
            height=packed.shape[0],    # rows - 1
            width=packed.shape[1],     # cols - 1
            count=1,
            dtype="uint16",
            crs=da.rio.crs,
            transform=new_transform,
        ) as dst:
            dst.write(packed, 1)

        return tmp, SCALE, OFFSET

    def _compute_slope(self, dtm_file: Path, tile_id: int) -> Tuple[Path, float, float]:
        """
        Compute slope (degrees) from the buffered DTM, crop the border pixels,
        and write an uncompressed intermediate GeoTIFF for gdal_translate.
        Returns the path to the intermediate file.
        """
        dtm = rxr.open_rasterio(dtm_file).squeeze()
        res = abs(float(dtm.rio.resolution()[0]))

        dz_dx, dz_dy = np.gradient(dtm.values, res, res)
        slope = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))

        # Pack slope into uint16 using a scale_factor / add_offset convention
        # (identical to NetCDF packing): unpacked = packed * scale_factor + add_offset
        # scale_factor=0.1, add_offset=0.0  →  0.1° precision, range 0–6553.5°
        SCALE = 0.1
        OFFSET = 0.0
        slope_packed = np.clip(
            np.round((slope - OFFSET) / SCALE), 0, np.iinfo(np.uint16).max
        ).astype(np.uint16)

        # Strip the 1-pixel border used to avoid edge artefacts
        b = self.BUFFER_PIXELS
        slope_da = xr.DataArray(
            slope_packed[b:-b, b:-b],
            coords={"y": dtm.y.values[b:-b], "x": dtm.x.values[b:-b]},
            dims=("y", "x"),
            name="slope",
        )
        slope_da.rio.write_crs(dtm.rio.crs, inplace=True)
        # Do NOT set scale_factor/add_offset in attrs here — rioxarray would
        # treat them as CF conventions and rescale the array back to float on
        # write. Instead, stamp them onto the COG band via gdal_translate -mo.

        tmp_file = self.output_dir / f"slope_tile_{tile_id}_tmp.tif"
        slope_da.rio.to_raster(tmp_file)
        return tmp_file, SCALE, OFFSET

    def _write_cog(
        self, src: Path, dst: Path, tile_id: int,
        scale: float | None = None, offset: float | None = None,
    ):
        """
        Convert an intermediate GeoTIFF to a web-optimised COG via gdal_translate:
          - 256×256 blocks  (matches web-map tile size)
          - ZSTD compression with PREDICTOR=2
          - Full AUTO overview pyramid with AVERAGE resampling
          - Optional scale_factor / add_offset stamped as band metadata tags
            so that rasterio / GDAL readers can auto-unpack packed integers.
        """
        cmd = [
            "gdal_translate",
            "-of", "COG",
            "-co", "BLOCKSIZE=256",
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


if __name__ == "__main__":
    load_dotenv()

    dtm_ingestor = DTMIngestor(
        stac_api="https://datacube.services.geo.ca/stac/api/",
        geojson_path="./data/aoi/test_aoi.geojson",
        output_dir="./data/tiles/",
        tile_size=8192,
        compute_slope=False,
        compute_relief=True,
    )
    dtm_ingestor.setup_r2_client(
        os.getenv("R2_ACCESS_KEY_ID"),
        os.getenv("R2_SECRET_ACCESS_KEY"),
        os.getenv("R2_S3_ENDPOINT"),
        os.getenv("R2_BUCKET"),
    )
    dtm_ingestor.create_tiles()
