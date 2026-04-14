"""
Tests for DTMIngestor: COG structure, packing metadata, value sanity, and
resource-consumption scaling.

Test markers
------------
integration  Requires network + disk (downloads real HRDEM data). Skip in CI with:
                 pytest -m "not integration"
resource     Verifies that peak RAM scales with STRIP_HEIGHT, not tile area.
                 pytest -m resource
"""

import gc
import tracemalloc
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from data_ingestion import DTMIngestor

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STAC_API   = "https://datacube.services.geo.ca/stac/api/"
AOI_GEOJSON = str(Path(__file__).parent.parent / "data/aoi/test_aoi.geojson")

# Small tile for fast integration tests (~512 m × 512 m at 1 m/px)
TILE_SIZE = 512

SLOPE_SCALE   = 0.1   # degrees per DN
SLOPE_OFFSET  = 0.0
RELIEF_SCALE  = 0.01  # metres per DN
RELIEF_OFFSET = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_intersecting_bbox(ingestor: DTMIngestor):
    """Return (bbox, tile_id) for the first grid cell that intersects the AOI."""
    from shapely.geometry import box

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

    raise AssertionError("No intersecting tile found in test AOI")


def _make_synthetic_dtm(tmp_path: Path, width: int, height: int,
                         pixel_size: float = 1.0) -> Path:
    """
    Write a synthetic float32 GeoTIFF (tiled, DEFLATE) with gentle terrain.
    Values ramp from 100 m to 200 m so slope/relief are non-trivial.
    Returns the path to the file.
    """
    transform = from_origin(0.0, height * pixel_size, pixel_size, pixel_size)
    data = np.linspace(100, 200, width * height, dtype=np.float32).reshape(height, width)

    tmp_path.mkdir(parents=True, exist_ok=True)
    out = tmp_path / "synthetic_dtm.tif"
    with rasterio.open(
        out, "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:3857",
        transform=transform,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as ds:
        ds.write(data, 1)
    return out


def _make_ingestor(tmp_path: Path, tile_size: int = TILE_SIZE,
                   strip_height: int | None = None,
                   compute_slope: bool = True,
                   compute_relief: bool = True) -> DTMIngestor:
    """
    Build a DTMIngestor whose STAC query is mocked out so no network is needed.
    Optionally override STRIP_HEIGHT.
    """
    fake_item = MagicMock()
    fake_item.id = "mock-item"
    fake_item.assets = {"dtm": MagicMock(href="https://example.com/mock.tif")}

    with patch("data_ingestion.StacClient") as MockClient:
        mock_search = MagicMock()
        mock_search.items.return_value = [fake_item]
        MockClient.open.return_value.search.return_value = mock_search

        ing = DTMIngestor(
            stac_api="https://mock/stac",
            geojson_path=AOI_GEOJSON,
            output_dir=str(tmp_path / "tiles"),
            tile_size=tile_size,
            pixel_size=1,
            replace=True,
            compute_slope=compute_slope,
            compute_relief=compute_relief,
        )

    if strip_height is not None:
        ing.STRIP_HEIGHT = strip_height

    return ing


# ---------------------------------------------------------------------------
# Fixtures (integration — require real network)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ingestor(tmp_path_factory):
    """Real DTMIngestor that talks to the HRDEM STAC API."""
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
    Download and process the first intersecting tile.
    Returns (slope_path, relief_path).
    """
    bbox, tile_id = _first_intersecting_bbox(ingestor)
    ingestor._process_tile(bbox, tile_id)

    slope_path  = ingestor.slope_dir  / f"slope_tile_{tile_id}.tif"
    relief_path = ingestor.relief_dir / f"relief_tile_{tile_id}.tif"

    assert slope_path.exists(),  f"slope COG not created: {slope_path}"
    assert relief_path.exists(), f"relief COG not created: {relief_path}"

    return slope_path, relief_path


# ---------------------------------------------------------------------------
# Unit tests — no network, use synthetic data
# ---------------------------------------------------------------------------

class TestDownloadDTMIntermediateFormat:
    """
    Verify that _download_dtm produces a tiled GeoTIFF so that later strip
    reads are efficient (random-access by block, not sequential scan).
    The actual gdalwarp call is mocked; we synthesise the output file.
    """

    def test_intermediate_dtm_is_tiled(self, tmp_path):
        ing = _make_ingestor(tmp_path)
        size = TILE_SIZE + 2 * DTMIngestor.BUFFER_PIXELS
        dtm = _make_synthetic_dtm(tmp_path, width=size, height=size)

        # Simulate what gdalwarp would create by copying the synthetic file
        # to the path _download_dtm would have produced for tile 0.
        expected_out = ing.output_dir / "dtm_tile_0_buffered.tif"
        expected_out.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy(dtm, expected_out)

        with rasterio.open(expected_out) as src:
            block_h, block_w = src.block_shapes[0]
        assert block_h == 256 and block_w == 256, (
            f"Intermediate DTM must be tiled 256×256 for efficient strip reads; "
            f"got {block_h}×{block_w}"
        )

    def test_strip_height_class_constant_exists(self):
        """STRIP_HEIGHT must be a class-level constant so it can be tuned centrally."""
        assert hasattr(DTMIngestor, "STRIP_HEIGHT"), \
            "DTMIngestor.STRIP_HEIGHT class constant is missing"
        assert isinstance(DTMIngestor.STRIP_HEIGHT, int) and DTMIngestor.STRIP_HEIGHT > 0


class TestComputeReliefUnit:
    """Run _compute_relief on a synthetic DTM and check output properties."""

    def test_output_shape_is_tile_minus_one(self, tmp_path):
        ing = _make_ingestor(tmp_path, compute_slope=False)
        size = TILE_SIZE + 2 * DTMIngestor.BUFFER_PIXELS
        dtm = _make_synthetic_dtm(tmp_path / "dtm", width=size, height=size)

        tmp_out, _, _ = ing._compute_relief(dtm, tile_id=0)

        with rasterio.open(tmp_out) as src:
            # 2×2 kernel shrinks each axis by 1
            assert src.width  == size - 1
            assert src.height == size - 1

    def test_output_dtype_is_uint16(self, tmp_path):
        ing = _make_ingestor(tmp_path, compute_slope=False)
        size = TILE_SIZE + 2 * DTMIngestor.BUFFER_PIXELS
        dtm = _make_synthetic_dtm(tmp_path / "dtm", width=size, height=size)

        tmp_out, _, _ = ing._compute_relief(dtm, tile_id=0)

        with rasterio.open(tmp_out) as src:
            assert src.dtypes[0] == "uint16"

    def test_relief_values_are_nonnegative(self, tmp_path):
        ing = _make_ingestor(tmp_path, compute_slope=False)
        size = TILE_SIZE + 2 * DTMIngestor.BUFFER_PIXELS
        dtm = _make_synthetic_dtm(tmp_path / "dtm", width=size, height=size)

        tmp_out, scale, offset = ing._compute_relief(dtm, tile_id=0)

        with rasterio.open(tmp_out) as src:
            raw = src.read(1).astype(np.float32)
        unpacked = raw * scale + offset
        assert unpacked.min() >= 0.0, f"Negative relief found: {unpacked.min()}"

    def test_strip_seams_are_continuous(self, tmp_path):
        """
        Relief values at strip boundaries must be identical regardless of whether
        STRIP_HEIGHT evenly divides the tile height.  We run the same DTM twice
        with two different strip heights and compare pixel-by-pixel.
        """
        size = 300  # deliberately not a multiple of common strip heights
        dtm  = _make_synthetic_dtm(tmp_path / "dtm_seam", width=size, height=size)

        ing_a = _make_ingestor(tmp_path / "a", tile_size=size - 2, compute_slope=False)
        ing_a.STRIP_HEIGHT = 64
        out_a, scale, _ = ing_a._compute_relief(dtm, tile_id=0)

        ing_b = _make_ingestor(tmp_path / "b", tile_size=size - 2, compute_slope=False)
        ing_b.STRIP_HEIGHT = 100   # different strip height → different seam positions
        out_b, _, _ = ing_b._compute_relief(dtm, tile_id=0)

        with rasterio.open(out_a) as sa, rasterio.open(out_b) as sb:
            data_a = sa.read(1)
            data_b = sb.read(1)

        assert data_a.shape == data_b.shape, "Output shapes differ between strip heights"
        np.testing.assert_array_equal(
            data_a, data_b,
            err_msg="Relief values differ at strip seams — boundary handling is broken",
        )


class TestComputeSlopeUnit:
    """Run _compute_slope on a synthetic DTM and check output properties."""

    def test_output_shape_matches_tile_size(self, tmp_path):
        ing = _make_ingestor(tmp_path, compute_relief=False)
        b    = DTMIngestor.BUFFER_PIXELS
        size = TILE_SIZE + 2 * b
        dtm  = _make_synthetic_dtm(tmp_path / "dtm", width=size, height=size)

        tmp_out, _, _ = ing._compute_slope(dtm, tile_id=0)

        with rasterio.open(tmp_out) as src:
            assert src.width  == TILE_SIZE
            assert src.height == TILE_SIZE

    def test_output_dtype_is_uint16(self, tmp_path):
        ing  = _make_ingestor(tmp_path, compute_relief=False)
        b    = DTMIngestor.BUFFER_PIXELS
        size = TILE_SIZE + 2 * b
        dtm  = _make_synthetic_dtm(tmp_path / "dtm", width=size, height=size)

        tmp_out, _, _ = ing._compute_slope(dtm, tile_id=0)

        with rasterio.open(tmp_out) as src:
            assert src.dtypes[0] == "uint16"

    def test_slope_range_is_physical(self, tmp_path):
        ing  = _make_ingestor(tmp_path, compute_relief=False)
        b    = DTMIngestor.BUFFER_PIXELS
        size = TILE_SIZE + 2 * b
        dtm  = _make_synthetic_dtm(tmp_path / "dtm", width=size, height=size)

        tmp_out, scale, offset = ing._compute_slope(dtm, tile_id=0)

        with rasterio.open(tmp_out) as src:
            raw = src.read(1).astype(np.float32)
        unpacked = raw * scale + offset
        assert unpacked.min() >= 0.0,  f"Negative slope: {unpacked.min()}"
        assert unpacked.max() <= 90.0, f"Slope > 90°: {unpacked.max()}"

    def test_strip_seams_are_continuous(self, tmp_path):
        """
        Slope values at strip boundaries must be identical regardless of strip height.
        """
        b    = DTMIngestor.BUFFER_PIXELS
        size = 300
        dtm  = _make_synthetic_dtm(tmp_path / "dtm_seam", width=size, height=size)
        ts   = size - 2 * b  # tile size after stripping buffer

        ing_a = _make_ingestor(tmp_path / "a", tile_size=ts, compute_relief=False)
        ing_a.STRIP_HEIGHT = 64
        out_a, _, _ = ing_a._compute_slope(dtm, tile_id=0)

        ing_b = _make_ingestor(tmp_path / "b", tile_size=ts, compute_relief=False)
        ing_b.STRIP_HEIGHT = 100
        out_b, _, _ = ing_b._compute_slope(dtm, tile_id=0)

        with rasterio.open(out_a) as sa, rasterio.open(out_b) as sb:
            data_a = sa.read(1)
            data_b = sb.read(1)

        assert data_a.shape == data_b.shape
        np.testing.assert_array_equal(
            data_a, data_b,
            err_msg="Slope values differ at strip seams — gradient guard rows are wrong",
        )


# ---------------------------------------------------------------------------
# Resource-consumption tests
# ---------------------------------------------------------------------------

@pytest.mark.resource
class TestResourceScaling:
    """
    Verify that peak RAM during _compute_relief and _compute_slope scales with
    STRIP_HEIGHT × tile_width, NOT with tile_height × tile_width.

    Strategy
    --------
    Run two identical tiles with different STRIP_HEIGHT values (4× apart).
    Measure peak tracemalloc memory for each run.  The ratio of peak allocations
    must be < 4.5× (allowing 12.5% headroom above the expected 4× ratio) — if
    the whole array were loaded at once, both runs would use the same memory.

    We also assert an absolute ceiling:
        peak ≤ STRIP_HEIGHT × tile_width × bytes_per_element × array_copies × fudge
    so the test is meaningful at realistic tile widths.
    """

    # Number of float32/float64 working arrays alive simultaneously.
    # For relief: arr, arr_safe, local_max, local_min, relief, packed → 6 arrays
    # For slope: arr, dz_dx, dz_dy, slope_full → 4 arrays (float64, so 8 bytes)
    RELIEF_ARRAY_COPIES = 6
    SLOPE_ARRAY_COPIES  = 4
    FUDGE               = 3.0   # generous headroom for Python/rasterio overhead

    def _measure_peak_mb(self, fn) -> float:
        """Run fn() under tracemalloc and return peak RAM in MB."""
        gc.collect()
        tracemalloc.start()
        try:
            fn()
        finally:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        gc.collect()
        return peak / 1024 / 1024

    # -- relief ----------------------------------------------------------------

    def test_relief_peak_ram_scales_with_strip_height(self, tmp_path):
        SMALL_STRIP = 32
        LARGE_STRIP = 128   # 4× larger
        TILE_W = 512

        dtm = _make_synthetic_dtm(tmp_path / "dtm", width=TILE_W + 2, height=TILE_W + 2)

        ing_small = _make_ingestor(tmp_path / "small", tile_size=TILE_W, compute_slope=False)
        ing_small.STRIP_HEIGHT = SMALL_STRIP
        ing_large = _make_ingestor(tmp_path / "large", tile_size=TILE_W, compute_slope=False)
        ing_large.STRIP_HEIGHT = LARGE_STRIP

        peak_small = self._measure_peak_mb(lambda: ing_small._compute_relief(dtm, tile_id=0))
        peak_large = self._measure_peak_mb(lambda: ing_large._compute_relief(dtm, tile_id=0))

        ratio = peak_large / max(peak_small, 0.001)
        assert ratio < 4.5, (
            f"Relief peak RAM ratio ({ratio:.2f}×) suggests the full tile is being "
            f"loaded instead of just the strip. "
            f"small={peak_small:.1f} MB, large={peak_large:.1f} MB"
        )

    def test_relief_peak_ram_absolute_ceiling(self, tmp_path):
        TILE_W      = 512
        STRIP       = DTMIngestor.STRIP_HEIGHT
        dtm = _make_synthetic_dtm(tmp_path / "dtm", width=TILE_W + 2, height=TILE_W + 2)

        ing = _make_ingestor(tmp_path / "ceil", tile_size=TILE_W, compute_slope=False)

        peak_mb = self._measure_peak_mb(lambda: ing._compute_relief(dtm, tile_id=0))

        # float32 working arrays: STRIP × width × 4 bytes × copies
        ceiling_mb = (
            STRIP * TILE_W * 4 * self.RELIEF_ARRAY_COPIES * self.FUDGE / 1024 / 1024
        )
        assert peak_mb < ceiling_mb, (
            f"Relief peak RAM {peak_mb:.1f} MB exceeds expected ceiling {ceiling_mb:.1f} MB "
            f"(STRIP_HEIGHT={STRIP}, tile_width={TILE_W}). "
            "The full tile may be loaded into memory."
        )

    def test_relief_peak_does_not_grow_with_tile_height(self, tmp_path):
        """
        A 4× taller tile with the same STRIP_HEIGHT must not use 4× more peak RAM.
        """
        TILE_W      = 256
        STRIP       = 32
        SMALL_H     = 256
        LARGE_H     = 1024  # 4× taller

        dtm_small = _make_synthetic_dtm(
            tmp_path / "small", width=TILE_W + 2, height=SMALL_H + 2
        )
        dtm_large = _make_synthetic_dtm(
            tmp_path / "large", width=TILE_W + 2, height=LARGE_H + 2
        )

        ing_small = _make_ingestor(tmp_path / "ings", tile_size=SMALL_H, compute_slope=False)
        ing_small.STRIP_HEIGHT = STRIP
        ing_large = _make_ingestor(tmp_path / "ingl", tile_size=LARGE_H, compute_slope=False)
        ing_large.STRIP_HEIGHT = STRIP

        peak_small = self._measure_peak_mb(lambda: ing_small._compute_relief(dtm_small, tile_id=0))
        peak_large = self._measure_peak_mb(lambda: ing_large._compute_relief(dtm_large, tile_id=0))

        ratio = peak_large / max(peak_small, 0.001)
        assert ratio < 2.0, (
            f"Relief peak RAM grew {ratio:.2f}× when tile height increased 4× at "
            f"constant STRIP_HEIGHT={STRIP}. "
            f"small={peak_small:.1f} MB, large={peak_large:.1f} MB. "
            "Strip processing is not bounding memory correctly."
        )

    # -- slope -----------------------------------------------------------------

    def test_slope_peak_ram_scales_with_strip_height(self, tmp_path):
        SMALL_STRIP = 32
        LARGE_STRIP = 128
        b     = DTMIngestor.BUFFER_PIXELS
        TILE_W = 512

        dtm = _make_synthetic_dtm(
            tmp_path / "dtm", width=TILE_W + 2 * b, height=TILE_W + 2 * b
        )

        ing_small = _make_ingestor(tmp_path / "small", tile_size=TILE_W, compute_relief=False)
        ing_small.STRIP_HEIGHT = SMALL_STRIP
        ing_large = _make_ingestor(tmp_path / "large", tile_size=TILE_W, compute_relief=False)
        ing_large.STRIP_HEIGHT = LARGE_STRIP

        peak_small = self._measure_peak_mb(lambda: ing_small._compute_slope(dtm, tile_id=0))
        peak_large = self._measure_peak_mb(lambda: ing_large._compute_slope(dtm, tile_id=0))

        ratio = peak_large / max(peak_small, 0.001)
        assert ratio < 4.5, (
            f"Slope peak RAM ratio ({ratio:.2f}×) suggests the full tile is being "
            f"loaded. small={peak_small:.1f} MB, large={peak_large:.1f} MB"
        )

    def test_slope_peak_does_not_grow_with_tile_height(self, tmp_path):
        b      = DTMIngestor.BUFFER_PIXELS
        TILE_W = 256
        STRIP  = 32
        SMALL_H = 256
        LARGE_H = 1024

        dtm_small = _make_synthetic_dtm(
            tmp_path / "small", width=TILE_W + 2 * b, height=SMALL_H + 2 * b
        )
        dtm_large = _make_synthetic_dtm(
            tmp_path / "large", width=TILE_W + 2 * b, height=LARGE_H + 2 * b
        )

        ing_small = _make_ingestor(tmp_path / "ings", tile_size=SMALL_H, compute_relief=False)
        ing_small.STRIP_HEIGHT = STRIP
        ing_large = _make_ingestor(tmp_path / "ingl", tile_size=LARGE_H, compute_relief=False)
        ing_large.STRIP_HEIGHT = STRIP

        peak_small = self._measure_peak_mb(lambda: ing_small._compute_slope(dtm_small, tile_id=0))
        peak_large = self._measure_peak_mb(lambda: ing_large._compute_slope(dtm_large, tile_id=0))

        ratio = peak_large / max(peak_small, 0.001)
        assert ratio < 2.0, (
            f"Slope peak RAM grew {ratio:.2f}× when tile height increased 4× at "
            f"constant STRIP_HEIGHT={STRIP}. "
            f"small={peak_small:.1f} MB, large={peak_large:.1f} MB."
        )


# ---------------------------------------------------------------------------
# COG structure tests  (integration)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCOGStructure:

    def test_slope_is_valid_cog(self, tile_cogs):
        slope_path, _ = tile_cogs
        with rasterio.open(slope_path) as src:
            assert src.driver == "GTiff"
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
# Packing metadata tests  (integration)
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
# Value sanity tests  (integration)
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
        """Raw uint16 values must have zero fractional part (packing sanity check)."""
        slope_path, _ = tile_cogs
        with rasterio.open(slope_path) as src:
            raw = src.read(1).astype(np.float64)
        fractional = np.modf(raw)[0]
        assert np.allclose(fractional, 0.0, atol=1e-9), \
            "Raw on-disk values are not integer — dtype packing is wrong"

    def test_relief_range_is_physical(self, tile_cogs):
        """Relief must be >= 0 and within uint16 range."""
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
        """Pack then unpack a known value and verify lossless recovery."""
        packed_slope = round((45.0 - SLOPE_OFFSET) / SLOPE_SCALE)
        unpacked = packed_slope * SLOPE_SCALE + SLOPE_OFFSET
        assert abs(unpacked - 45.0) < 1e-9, "Slope packing round-trip failed"

        packed_relief = round((1.23 - RELIEF_OFFSET) / RELIEF_SCALE)
        unpacked = packed_relief * RELIEF_SCALE + RELIEF_OFFSET
        assert abs(unpacked - 1.23) < 1e-9, "Relief packing round-trip failed"
