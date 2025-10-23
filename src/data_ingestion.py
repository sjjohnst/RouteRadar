"""
This script extracts DTM data over an input AOI defined in geojson format.
Source:
- https://ftp.maps.canada.ca/pub/elevation/dem_mne/highresolution_hauteresolution/dtm_mnt/
OR STAC APIs
- https://datacube.services.geo.ca/stac/api/search?collections=hrdem-lidar
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
    The DTMIngestor class handles connection to the STAC API, and can be queried 
    to extract DTM data over a specified Area of Interest (AOI).
    """
    def __init__(self, stac_api_url: str):
        # Connect to the STAC API
        self.client = Client.open(stac_api_url)
        
        # Subset to the DTM collection (hrdem-mosaic-1m)
        self.collection = ["hrdem-mosaic-1m"]
    
    def extract_dtm(self, aoi_geojson: str) -> xr.DataArray:
        """
        Extract DTM data over the specified AOI, returning the physical DTM data in raster format.
        Args:
            aoi_geojson (str): Path to the geojson file defining the AOI.
        Returns:
            dtm_raster (xr.DataArray): The extracted DTM data as a raster.
        """
        # Load the AOI geojson and convert to geometry
        aoi_geometry = self._prepare_aoi_geometry(aoi_geojson)        
        
        # Query the STAC API for items covering the AOI
        items = self._query_aoi(aoi_geometry)
        
        # Now we want to extract the DTM from these items, but only where they intersect the AOI
        dtm_arrays = [self._extract_dtm_from_item(item, aoi_geometry) for item in items]
        
        # Combine the DTM arrays (assuming they align properly)
        if len(dtm_arrays) > 1:
            dtm_raster = rxr.merge.merge_arrays(dtm_arrays)
        else:
            dtm_raster = dtm_arrays[0]
        
        # Load the DTM data into memory for the final output
        dtm_raster = dtm_raster.load()
        
        return dtm_raster
        
    def _prepare_aoi_geometry(self, aoi_geojson: str) -> dict:
        """
        Load the AOI geojson file and extract the geometry.
        Args:
            aoi_geojson (str): Path to the geojson file defining the AOI.
        Returns:
            geometry (dict): The geometry of the AOI.
        """
        
        # Load the geojson file
        with open(aoi_geojson, 'r') as f:
            aoi_data = json.load(f)
        
        # Extract the geometry
        geometry = aoi_data['geometry']

        return geometry
    
    def _query_aoi(self, aoi_geometry: dict) -> list:
        """
        Given an AOI in geojson format, query the STAC API for DTM data.
        Args:
            aoi_geometry (dict): The geometry of the AOI from the geojson file.
        Returns:
            items (list): List of STAC items covering the AOI.
        """
        # Search the STAC API for items intersecting the AOI
        search_results = self.client.search(
            collections=self.collection,
            intersects=aoi_geometry,
            max_items=2
        )
        
        # Retrieve the matched items
        items = list(search_results.items())
        
        return items

    def _extract_dtm_from_item(self, item, aoi_geometry: dict) -> xr.DataArray:
        """
        Extract the DTM data from a single STAC item, clipped to the AOI geometry.
        Args:
            item: A STAC item containing DTM data.
            aoi_geometry (dict): The geometry of the AOI.
        Returns:
            dtm_raster (xr.DataArray): The extracted DTM data as a raster.
        """
        # Get the asset URL for the DTM data
        dtm_asset = item.assets['dtm']
        dtm_url = dtm_asset.href
        
        # Load the DTM data using xarray
        dtm_data = rxr.open_rasterio(dtm_url, chunks=True)

        # Get the coordinates and bounding box of the AOI
        coords = np.array(aoi_geometry["coordinates"][0])
        bbox = [coords[:,0].min(), coords[:,1].min(), coords[:,0].max(), coords[:,1].max()]
        crs = "EPSG:4326"

        # Clip the DTM data to the bounding box (memory efficient)
        dtm_clipped = dtm_data.rio.clip_box(minx=bbox[0], miny=bbox[1],
                                           maxx=bbox[2], maxy=bbox[3],
                                           crs=crs)
        
        # Now clip to the AOI polygon
        dtm_clipped = dtm_clipped.rio.clip([aoi_geometry], crs=crs, drop=True, invert=False)
        
        # Return the clipped DTM data
        return dtm_clipped


if __name__ == "__main__":
    
    parser = ArgumentParser(description="Extract DTM data over an AOI from STAC API")
    parser.add_argument("--aoi", type=str, required=True, help="Path to the AOI geojson file")
    args = parser.parse_args()
    
    aoi_geojson_path = args.aoi    
    stac_api_url = "https://datacube.services.geo.ca/stac/api/"
    
    dtm_ingestor = DTMIngestor(stac_api_url)
    dtm_raster = dtm_ingestor.extract_dtm(aoi_geojson_path)

    print(dtm_raster)
    
    # Optionally, save the DTM raster to a file
    output_dir = "data/dtm/"
    file_name = os.path.splitext(os.path.basename(aoi_geojson_path))[0] + "_dtm.tif"
    output_path = os.path.join(output_dir, file_name)
    os.makedirs(output_dir, exist_ok=True)
    dtm_raster.rio.to_raster(output_path)
    print(f"DTM raster saved to: {output_path}")
