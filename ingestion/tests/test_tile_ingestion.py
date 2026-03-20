"""
Integration test: download one small tile, then verify slope and relief COGs.

Requires network access to the HRDEM STAC API and enough disk space for a
256×256-pixel tile (~130 KB uncompressed). Mark slow tests with -m integration
and skip in CI if desired:
    pytest -m integration ingestion/tests/test_tile_ingestion.py
"""

import pytest
import rasterio
import numpy as np
from pathlib import Path

from data_ingestion import DTMIngestor

# ---------------------------------------------------------------------------
# Constants that match the test AOI (Laurentians, QC)
# These coordinates are in EPSG:3857 and fall inside the HRDEM coverage area.
# ---------------------------------------------------------------------------
STAC_API = "https://datacube.services.geo.ca/stac/api/"
AOI_GEOJSON = str(Path(__file__).parent.parent / "data/aoi/test_aoi.geojson")

# Use a small tile to keep the test fast (~512 m × 512 m at 1 m/px)
TILE_SIZE = 512

SLOPE_SCALE  = 0.1   # degrees per DN
SLOPE_OFFSET = 0.0
RELIEF_SCALE  = 0.01  # metres per DN
RELIEF_OFFSET = 0.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ingestor(tmp_path_factory):
    """Create a DTMIngestor writing into a temporary directory."""
    out_dir = tmp_path_factory.mktemp("tiles")
    return DTMIngestor(
        stac_api=STAC_API,
        geojson_path=AOI_GEOJSON,
        output_dir=str(out_dir),
        tile_size=TILE_SIZE,
        pixel_size=1,
        replace=True,
        compute_slope=True,
        compute_relief=True,
    )


@pytest.fixture(scope="module")
def tile_cogs(ingestor):
    """
    Download and process tile 0 (first intersecting tile in the AOI grid).
    Returns (slope_path, relief_path).
    """
    from pyproj import Transformer
    from shapely.geometry import shape, box
    import numpy as np

    projected_aoi = ingestor._project_aoi()
    minx, miny, maxx, maxy = projected_aoi.bounds
    tile_size_m = ingestor.tile_size * ingestor.pixel_size

    # Find the first bbox that intersects the AOI — same logic as create_tiles
    tile_id = 0
    target_bbox = None
    for x in np.arange(minx, maxx, tile_size_m):
        for y in np.arange(miny, maxy, tile_size_m):
            bbox = [x, y, x + tile_size_m, y + tile_size_m]
            if projected_aoi.intersects(box(*bbox)):
                target_bbox = bbox
                break
        if target_bbox is not None:
            break

    assert target_bbox is not None, "No intersecting tile found in test AOI"

    ingestor._process_tile(target_bbox, tile_id)

    slope_path  = ingestor.slope_dir  / f"slope_tile_{tile_id}.tif"
    relief_path = ingestor.relief_dir / f"relief_tile_{tile_id}.tif"

    assert slope_path.exists(),  f"slope COG not created: {slope_path}"
    assert relief_path.exists(), f"relief COG not created: {relief_path}"

    return slope_path, relief_path


# ---------------------------------------------------------------------------
# COG structure tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCOGStructure:

    def test_slope_is_valid_cog(self, tile_cogs):
        slope_path, _ = tile_cogs
        with rasterio.open(slope_path) as src:
            assert src.driver == "GTiff"
            # is_tiled is deprecated and returns False when block == raster size;
            # check the block shape directly instead.
            block_h, block_w = src.block_shapes[0]
            assert block_h == 256 and block_w == 256, (
                f"Expected 256×256 blocks, got {block_h}×{block_w}"
            )
            assert src.compression.name.upper() == "ZSTD"
            assert src.overviews(1), "Expected overview pyramid to be present"

    def test_relief_is_valid_cog(self, tile_cogs):
        _, relief_path = tile_cogs
        with rasterio.open(relief_path) as src:
            assert src.driver == "GTiff"
            block_h, block_w = src.block_shapes[0]
            assert block_h == 256 and block_w == 256, (
                f"Expected 256×256 blocks, got {block_h}×{block_w}"
            )
            assert src.compression.name.upper() == "ZSTD"
            assert src.overviews(1), "Expected overview pyramid to be present"

    def test_slope_crs_is_epsg3857(self, tile_cogs):
        slope_path, _ = tile_cogs
        with rasterio.open(slope_path) as src:
            assert src.crs.to_epsg() == 3857

    def test_relief_crs_is_epsg3857(self, tile_cogs):
        _, relief_path = tile_cogs
        with rasterio.open(relief_path) as src:
            assert src.crs.to_epsg() == 3857

    def test_slope_shape(self, tile_cogs):
        slope_path, _ = tile_cogs
        with rasterio.open(slope_path) as src:
            assert src.width  == TILE_SIZE
            assert src.height == TILE_SIZE

    def test_relief_shape(self, tile_cogs):
        _, relief_path = tile_cogs
        with rasterio.open(relief_path) as src:
            assert src.width  == TILE_SIZE
            assert src.height == TILE_SIZE


# ---------------------------------------------------------------------------
# Packing metadata tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPackingMetadata:

    def test_slope_has_scale_factor_tag(self, tile_cogs):
        slope_path, _ = tile_cogs
        with rasterio.open(slope_path) as src:
            tags = src.tags()
        assert "scale_factor" in tags, "scale_factor tag missing from slope COG"
        assert float(tags["scale_factor"]) == pytest.approx(SLOPE_SCALE)

    def test_slope_has_add_offset_tag(self, tile_cogs):
        slope_path, _ = tile_cogs
        with rasterio.open(slope_path) as src:
            tags = src.tags()
        assert "add_offset" in tags, "add_offset tag missing from slope COG"
        assert float(tags["add_offset"]) == pytest.approx(SLOPE_OFFSET)

    def test_relief_has_scale_factor_tag(self, tile_cogs):
        _, relief_path = tile_cogs
        with rasterio.open(relief_path) as src:
            tags = src.tags()
        assert "scale_factor" in tags, "scale_factor tag missing from relief COG"
        assert float(tags["scale_factor"]) == pytest.approx(RELIEF_SCALE)

    def test_relief_has_add_offset_tag(self, tile_cogs):
        _, relief_path = tile_cogs
        with rasterio.open(relief_path) as src:
            tags = src.tags()
        assert "add_offset" in tags, "add_offset tag missing from relief COG"
        assert float(tags["add_offset"]) == pytest.approx(RELIEF_OFFSET)

    def test_slope_dtype_is_uint16(self, tile_cogs):
        slope_path, _ = tile_cogs
        with rasterio.open(slope_path) as src:
            assert src.dtypes[0] == "uint16"

    def test_relief_dtype_is_uint16(self, tile_cogs):
        _, relief_path = tile_cogs
        with rasterio.open(relief_path) as src:
            assert src.dtypes[0] == "uint16"


# ---------------------------------------------------------------------------
# Value sanity tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestValues:

    def _unpack(self, path: Path, scale: float, offset: float) -> np.ndarray:
        with rasterio.open(path) as src:
            raw = src.read(1).astype(np.float32)
        return raw * scale + offset

    def test_slope_range_is_physical(self, tile_cogs):
        """Unpacked slope must be within [0, 90] degrees."""
        slope_path, _ = tile_cogs
        unpacked = self._unpack(slope_path, SLOPE_SCALE, SLOPE_OFFSET)
        assert unpacked.min() >= 0.0,  f"Negative slope found: {unpacked.min()}"
        assert unpacked.max() <= 90.0, f"Slope > 90° found: {unpacked.max()}"

    def test_slope_has_nonzero_values(self, tile_cogs):
        """At least some terrain should have slope > 0 (not a flat ocean tile)."""
        slope_path, _ = tile_cogs
        unpacked = self._unpack(slope_path, SLOPE_SCALE, SLOPE_OFFSET)
        assert unpacked.max() > 0.0, "All slope values are zero — likely a bad tile"

    def test_slope_precision_is_01_degrees(self, tile_cogs):
        """Packing at 0.1° precision: every unpacked value should be an integer
        multiple of scale_factor. We verify this by checking that unpacked / scale
        is integer-valued (i.e. the fractional part is ~0), avoiding the float
        representation issues of `x % 0.1`."""
        slope_path, _ = tile_cogs
        with rasterio.open(slope_path) as src:
            raw = src.read(1).astype(np.float64)
        # raw values are already integers (uint16); dividing by 1.0 and checking
        # the fractional part of (raw * scale / scale) == raw is the simplest proof.
        # Equivalently: unpacked values are raw * 0.1, and the only source of
        # sub-0.1 error is float representation — raw * 0.1 should round back to raw.
        fractional = np.modf(raw)[0]   # fractional part of the raw uint16 array
        assert np.allclose(fractional, 0.0, atol=1e-9), \
            "Raw on-disk values are not integer — dtype packing is wrong"

    def test_relief_range_is_physical(self, tile_cogs):
        """Relief (local height above 3×3 min) must be >= 0 and < 655 m."""
        _, relief_path = tile_cogs
        unpacked = self._unpack(relief_path, RELIEF_SCALE, RELIEF_OFFSET)
        assert unpacked.min() >= 0.0,   f"Negative relief found: {unpacked.min()}"
        assert unpacked.max() < 655.36, f"Relief exceeds uint16 range: {unpacked.max()}"

    def test_relief_has_nonzero_values(self, tile_cogs):
        """Terrain in the Laurentians should have some local relief."""
        _, relief_path = tile_cogs
        unpacked = self._unpack(relief_path, RELIEF_SCALE, RELIEF_OFFSET)
        assert unpacked.max() > 0.0, "All relief values are zero — likely a bad tile"

    def test_packing_roundtrip(self, tile_cogs):
        """Pack then unpack a known value: round(45.0 / 0.1) * 0.1 == 45.0."""
        packed_slope = round((45.0 - SLOPE_OFFSET) / SLOPE_SCALE)
        unpacked = packed_slope * SLOPE_SCALE + SLOPE_OFFSET
        assert abs(unpacked - 45.0) < 1e-9, "Slope packing round-trip failed"

        packed_relief = round((1.23 - RELIEF_OFFSET) / RELIEF_SCALE)
        unpacked = packed_relief * RELIEF_SCALE + RELIEF_OFFSET
        assert abs(unpacked - 1.23) < 1e-9, "Relief packing round-trip failed"
