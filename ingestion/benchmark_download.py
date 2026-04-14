"""
benchmark_download.py — Measure DTM download throughput for a 32 km × 32 km tile.

Usage
-----
    python benchmark_download.py [--tile-size 32768] [--pixel-size 1] [--keep]

What it does
------------
1. Resolves the first grid cell that intersects the test AOI and has the
   requested dimensions.
2. Runs _download_dtm() once (the "warm-up" gdalwarp call that populates GDAL's
   /vsicurl/ cache on the remote server side).
3. Runs it a second time with replace=True so the download races against a cold
   local file, giving a realistic throughput figure.
4. Reports wall-clock time, file size, and MB/s for each run.
5. Optionally keeps the downloaded file for inspection.

"""

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
from shapely.geometry import box

# Allow running from the ingestion/ directory without installing the package
sys.path.insert(0, str(Path(__file__).parent))

from data_ingestion import DTMIngestor

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
STAC_API    = "https://datacube.services.geo.ca/stac/api/"
AOI_GEOJSON = str(Path(__file__).parent / "data/aoi/test_aoi.geojson")
OUT_DIR     = Path(__file__).parent / "data/benchmark_tiles"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_intersecting_bbox(ingestor: DTMIngestor) -> tuple[list[float], int]:
    """Return (bbox, tile_id) for the first AOI-intersecting grid cell."""
    projected_aoi = ingestor._project_aoi()
    minx, miny, maxx, maxy = projected_aoi.bounds
    tile_size_m = ingestor.tile_size * ingestor.pixel_size

    tile_id = 0
    for x in np.arange(minx, maxx, tile_size_m):
        for y in np.arange(miny, maxy, tile_size_m):
            bbox = [x, y, x + tile_size_m, y + tile_size_m]
            if projected_aoi.intersects(box(*bbox)):
                return bbox, tile_id
            tile_id += 1

    raise RuntimeError("No grid cell intersects the AOI — check AOI GeoJSON.")


def _fmt_size(path: Path) -> str:
    mb = path.stat().st_size / 1024 / 1024
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.1f} MB"


def _run_download(ingestor: DTMIngestor, bbox: list[float], tile_id: int,
                  label: str) -> tuple[float, float]:
    """
    Run _download_dtm, measure wall-clock time and throughput.
    Returns (elapsed_s, mb_per_s).
    """
    # Remove any pre-existing file so we time a real write
    out_file = ingestor.output_dir / f"dtm_tile_{tile_id}_buffered.tif"
    if out_file.exists():
        out_file.unlink()

    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    print(f"  bbox      : {[f'{v:.0f}' for v in bbox]}")
    print(f"  tile size : {ingestor.tile_size} px  ({ingestor.tile_size * ingestor.pixel_size / 1000:.1f} km)")
    print(f"  output    : {out_file}")
    print()

    t0 = time.perf_counter()
    ingestor._download_dtm(bbox, tile_id)
    elapsed = time.perf_counter() - t0

    size_mb  = out_file.stat().st_size / 1024 / 1024
    mb_per_s = size_mb / elapsed if elapsed > 0 else float("inf")

    print(f"  ✓  elapsed   : {elapsed:.1f} s")
    print(f"     file size : {_fmt_size(out_file)}")
    print(f"     throughput: {mb_per_s:.1f} MB/s")

    return elapsed, mb_per_s


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Benchmark DTM download for a large tile.")
    parser.add_argument("--tile-size",  type=int, default=2**15,
                        help="Tile edge length in pixels (default: 32768 → ~32 km at 1 m/px)")
    parser.add_argument("--pixel-size", type=int, default=1,
                        help="Metres per pixel (default: 1)")
    parser.add_argument("--keep", action="store_true",
                        help="Keep the downloaded file after the benchmark")
    parser.add_argument("--runs", type=int, default=2,
                        help="Number of download runs (default: 2; first is a warm-up)")
    parser.add_argument("--gdal-cache", type=int, default=1024,
                        help="GDAL block cache in MB passed to gdalwarp --config GDAL_CACHEMAX (default: 1024)")
    args = parser.parse_args()

    tile_km = args.tile_size * args.pixel_size / 1000
    uncompressed_gb = (args.tile_size ** 2 * 4) / 1024 ** 3

    # Diagnose connection latency upfront so slow results can be explained.
    import subprocess as _sp
    rtt_line = "(skipped)"
    try:
        rtt_result = _sp.run(
            ["ping", "-c", "3", "-q", "datacube.services.geo.ca"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        rtt_line = "(no output)"
        for line in rtt_result.stdout.splitlines():
            if "avg" in line or "rtt" in line:
                rtt_line = line.strip()
                break
        else:
            if rtt_result.stdout.strip():
                rtt_line = rtt_result.stdout.strip().splitlines()[-1]
    except (OSError, _sp.TimeoutExpired) as exc:
        rtt_line = f"(ping unavailable: {exc})"

    print()
    print("=" * 60)
    print("  DTM Download Benchmark")
    print("=" * 60)
    print(f"  tile size       : {args.tile_size} px  ({tile_km:.0f} km × {tile_km:.0f} km)")
    print(f"  pixel size      : {args.pixel_size} m/px")
    print(f"  uncompressed    : ~{uncompressed_gb:.1f} GB  (float32)")
    print(f"  runs            : {args.runs}  (run 1 = warm-up)")
    print(f"  output dir      : {OUT_DIR}")
    print(f"  GDAL_CACHEMAX   : {args.gdal_cache} MB")
    print("  HTTP merge/mpx  : YES / YES / 8 connections  (see _download_dtm)")
    print("  sidecar probes  : suppressed (GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR)")
    print("  source asset    : dtm-vrt (512×512 blocks, explicit overviews)")
    print(f"  server RTT      : {rtt_line}")
    print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ingestor = DTMIngestor(
        stac_api=STAC_API,
        geojson_path=AOI_GEOJSON,
        output_dir=str(OUT_DIR),
        tile_size=args.tile_size,
        pixel_size=args.pixel_size,
        replace=True,
        compute_slope=False,
        compute_relief=False,
    )

    bbox, tile_id = _first_intersecting_bbox(ingestor)

    results: list[tuple[float, float]] = []
    for i in range(args.runs):
        label = f"Run {i + 1} of {args.runs}" + ("  (warm-up)" if i == 0 else "")
        elapsed, mb_per_s = _run_download(ingestor, bbox, tile_id, label)
        results.append((elapsed, mb_per_s))

    # Summary
    out_file = ingestor.output_dir / f"dtm_tile_{tile_id}_buffered.tif"
    print()
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    for i, (elapsed, mb_per_s) in enumerate(results):
        tag = "warm-up" if i == 0 else f"run {i + 1}"
        print(f"  {tag:>10}  :  {elapsed:6.1f} s   {mb_per_s:6.1f} MB/s")

    if len(results) > 1:
        best_elapsed, best_throughput = min(results[1:], key=lambda r: r[0])
        print(f"  {'best':>10}  :  {best_elapsed:6.1f} s   {best_throughput:6.1f} MB/s")

    if not args.keep and out_file.exists():
        out_file.unlink()
        print()
        print("  (downloaded file removed — pass --keep to retain it)")

    print()


if __name__ == "__main__":
    main()
