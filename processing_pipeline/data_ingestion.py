import json
import os
import subprocess
import numpy as np
from shapely.geometry import shape, mapping, box
from pystac_client import Client as StacClient
import pyproj
from pyproj import Transformer

class DTMIngestor:
    """
    The DTMIngestor class handles connection to the STAC API and extracts
    merged DTM data over a specified Area of Interest (AOI).
    """

    def __init__(self, stac_api: str, geojson_path: str, output_dir: str, tile_size_m: int):
        self.output_dir = output_dir
        self.tile_size_m = tile_size_m
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Connect to the STAC API
        self.client = StacClient.open(stac_api)
        
        # Load AOI geometry
        self.aoi_geom = self.get_aoi_geometry(geojson_path)
        
        # Locate the asset url for the DTM mosaic
        self.items = self.query_stac_items(self.aoi_geom.bounds)
        if not self.items:
            raise ValueError("No items found for the given AOI.")

        # 2. Collect all DTM asset URLs
        # Prepend /vsicurl/ to each
        self.mosaic_urls = [f"/vsicurl/{item.assets['dtm'].href}" for item in self.items]
        
        print(f"Found {len(self.items)} STAC items intersecting your AOI.")
        for item in self.items:
            print(f" - Item: {item.id}")

    def create_tiles(self):       
        # Reproject AOI from EPSG:4326 to EPSG:3979
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:3979", always_xy=True)
        projected_coords = [transformer.transform(lon, lat) for lon, lat in self.aoi_geom.exterior.coords]
        projected_aoi = shape({'type': 'Polygon', 'coordinates': [projected_coords]})
        # print("AOI reprojected to EPSG:3979 for tiling.")
        
        minx, miny, maxx, maxy = projected_aoi.bounds

        # Generate Grid
        cols = list(np.arange(minx, maxx, self.tile_size_m))
        rows = list(np.arange(miny, maxy, self.tile_size_m))
        
        print(f"Creating a grid of {len(cols)} x {len(rows)} tiles...")
        
        tile_count = 0
        for x in cols:
            for y in rows:
                # Define tile bounding box
                tile_bbox = [x, y, x + self.tile_size_m, y + self.tile_size_m]
                
                # Check intersection with AOI
                tile_polygon = box(*tile_bbox)
                if not projected_aoi.intersects(tile_polygon):
                    print(f"Skipping tile at {tile_bbox}, no intersection with AOI.")
                    continue
                    
                self.download_tile(tile_bbox, tile_count)
                tile_count += 1
                break # Remove this break to process all tiles - DEBUGGING ONLY
            break # Remove this break to process all tiles - DEBUGGING ONLY

    def query_stac_items(self, bbox):
        """
        Query the STAC API for items intersecting the given bounding box.
        
        Args:
            bbox (list): Bounding box [minx, miny, maxx, maxy] in EPSG:4326.
        """
        search = self.client.search(
            collections=["hrdem-mosaic-1m"],
            bbox=bbox,
            limit=10
        )
        items = list(search.get_items())
        return items
    
    @staticmethod
    def get_aoi_geometry(geojson_path):
        with open(geojson_path, 'r') as f:
            aoi_data = json.load(f)
        return shape(aoi_data['geometry'] if 'geometry' in aoi_data else aoi_data)

    def download_tile(self, bbox, tile_id):
        # bbox is [minx, miny, maxx, maxy] in EPSG:3979
        output_file = os.path.join(self.output_dir, f"dtm_tile_{tile_id}.tif")
        
        if os.path.exists(output_file):
            print(f"Tile {tile_id} already exists, skipping...")
            return
        
        cmd = [
            "gdalwarp",
            "-multi", "-wo", "NUM_THREADS=ALL_CPUS",
            "-wm", "1024", 
            "--config", "GDAL_CACHEMAX", "2048",
            "--config", "GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR",
            "--config", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif",
            "-te", str(bbox[0]), str(bbox[1]), str(bbox[2]), str(bbox[3]),
            "-of", "COG",
            "-wo", "NUM_THREADS=ALL_CPUS", # Use all available cores
            "-co", "COMPRESS=DEFLATE",     # Lossless compression
            "-co", "PREDICTOR=2",          # Better compression for continuous data
            "-co", "NUM_THREADS=ALL_CPUS", # Parallelize the creation of the COG
            *self.mosaic_urls,
            output_file
        ]
        print(f"Slicing tile {tile_id} from remote mosaic...")
        subprocess.run(cmd, check=True)

if __name__ == "__main__":
    aoi_path = "./data/aoi/big_laurentides.geojson"
    output_dir = "./data/raw_tiles/"
    api_url = "https://datacube.services.geo.ca/stac/api/"
    tile_size_m = 15000  # Tile size in meters
    
    dtm_ingestor = DTMIngestor(stac_api=api_url, geojson_path=aoi_path, output_dir=output_dir, tile_size_m=tile_size_m)
    dtm_ingestor.create_tiles()
