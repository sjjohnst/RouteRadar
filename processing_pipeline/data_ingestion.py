"""
This script extracts DTM data over an input AOI defined in geojson format 
and saves it as a SINGLE Cloud Optimized GeoTIFF (COG).
Source: https://datacube.services.geo.ca/stac/api/search?collections=hrdem-lidar
"""

import os
import json
import rioxarray as rxr
import xarray as xr
import numpy as np
from pystac_client import Client
from argparse import ArgumentParser

class DTMIngestor:
    """
    The DTMIngestor class handles connection to the STAC API and extracts 
    merged DTM data over a specified Area of Interest (AOI).
    """
    def __init__(self, stac_api_url: str):
        # Connect to the STAC API
        self.client = Client.open(stac_api_url)
        # Subset to the DTM collection (hrdem-mosaic-1m)
        self.collection = ["hrdem-mosaic-1m"]

    def extract_dtm(self, aoi_geojson: str) -> xr.DataArray:
        """
        Extract DTM data over the specified AOI, merging all intersecting STAC items
        into a single raster.
        
        Args:
            aoi_geojson (str): Path to the geojson file defining the AOI.
        Returns:
            dtm_raster (xr.DataArray): The extracted DTM data as a raster.
        """
        aoi_geometry = self._prepare_aoi_geometry(aoi_geojson)
        items = self._query_aoi(aoi_geometry)
        
        if not items:
            raise ValueError("No STAC items found for the given AOI.")

        print(f"Found {len(items)} source tiles covering AOI. Merging...")
        
        dtm_arrays = [self._extract_dtm_from_item(item, aoi_geometry) for item in items]
        
        if len(dtm_arrays) > 1:
            dtm_raster = rxr.merge.merge_arrays(dtm_arrays)
        else:
            dtm_raster = dtm_arrays[0]
            
        # Reproject to Web Mercator (EPSG:3857) for web mapping compatibility
        print("Reprojecting to EPSG:3857...")
        dtm_raster_3857 = dtm_raster.rio.reproject("EPSG:3857")
        
        return dtm_raster_3857

    def _prepare_aoi_geometry(self, aoi_geojson: str) -> dict:
        """Load the AOI geojson file and extract the geometry."""
        with open(aoi_geojson, 'r') as f:
            aoi_data = json.load(f)
        return aoi_data['geometry']
    
    def _query_aoi(self, aoi_geometry: dict) -> list:
        """Given an AOI geometry, query the STAC API for DTM data."""
        search_results = self.client.search(
            collections=self.collection,
            intersects=aoi_geometry,
        )
        items = list(search_results.items())
        return items

    def _extract_dtm_from_item(self, item, aoi_geometry: dict) -> xr.DataArray:
        """Extract the DTM data from a single STAC item, clipped to the AOI."""
        dtm_asset = item.assets['dtm']
        dtm_url = dtm_asset.href
        
        # Load lazily with chunks
        dtm_data = rxr.open_rasterio(dtm_url, chunks=True)

        coords = np.array(aoi_geometry["coordinates"][0])
        bbox = [coords[:,0].min(), coords[:,1].min(), coords[:,0].max(), coords[:,1].max()]
        crs = "EPSG:4326"

        # Clip to bounding box first (efficient)
        dtm_clipped = dtm_data.rio.clip_box(
            minx=bbox[0], miny=bbox[1],
            maxx=bbox[2], maxy=bbox[3],
            crs=crs
        )
        
        # Precise clip to polygon geometry
        dtm_clipped = dtm_clipped.rio.clip([aoi_geometry], crs=crs, drop=True, invert=False)
        
        return dtm_clipped


if __name__ == "__main__":
    parser = ArgumentParser(description="Extract single merged DTM COG over an AOI.")
    parser.add_argument("--aoi", type=str, required=True, help="Path to the AOI geojson file")
    args = parser.parse_args()

    aoi_geojson_path = args.aoi
    stac_api_url = "https://datacube.services.geo.ca/stac/api/"

    dtm_ingestor = DTMIngestor(stac_api_url)

    output_dir = "data/dtm_cog/"
    os.makedirs(output_dir, exist_ok=True)
    
    # Construct output filename based on input name
    base_name = os.path.splitext(os.path.basename(aoi_geojson_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}_merged.tif")

    try:
        print(f"Starting extraction for {base_name}...")
        
        # 1. Extract and Reproject
        final_raster = dtm_ingestor.extract_dtm(aoi_geojson_path)
        
        print(f"Saving to {output_path}...")
        
        # 2. Save as Cloud Optimized GeoTIFF
        final_raster.rio.to_raster(
            output_path,
            driver="COG",
            compress="deflate",
            predictor=2, # Optimized for floating point data (DEMs)
            blocksize=512,
            overview_resampling="nearest",
            bigtiff="IF_NEEDED", # Handles files > 4GB automatically
            num_threads="ALL_CPUS"
        )
        
        print(f"Success! COG saved at: {output_path}")

    except Exception as e:
        print(f"Error during processing: {e}")