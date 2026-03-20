# RouteRadar

A geospatial web application for rock climbing route development. RouteRadar ingests high-resolution digital elevation model (HRDEM) data, computes slope and relief rasters, and serves them as interactive map tiles — helping climbers and route developers identify promising terrain features like cliffs and steep faces.

---

## Features

- **Interactive map** built with MapLibre GL, constrained to a configurable Area of Interest (AOI)
- **DTM tile ingestion** — downloads 1m HRDEM data from the Canadian STAC API, computes slope & hillshade relief, and produces Cloud-Optimized GeoTIFFs (COGs)
- **Cloudflare R2 storage** — COGs are uploaded to R2 and served on demand
- **TiTiler mosaic backend** — FastAPI service builds a MosaicJSON from all COGs in R2 at startup and serves raster tiles
- **Map toolkit** — click-to-query elevation, distance measurement, location search, and WMS layer toggles
- **Fully Dockerized** — single `docker compose` command to run the full stack

---

## Architecture

```
ingestion/          # Python pipeline: STAC → DTM → COG → R2
backend/            # FastAPI + TiTiler: serves mosaic raster tiles from R2
frontend/           # Vite + MapLibre GL: interactive map UI
```

**Data flow:**
1. `DTMIngestor` queries the HRDEM STAC API for 1m DTM tiles over the AOI
2. Each tile is reprojected to EPSG:3857, slope/relief computed, and written as a COG
3. COGs are uploaded to a Cloudflare R2 bucket
4. On startup, the backend lists all COGs in R2 and builds a MosaicJSON in memory
5. The frontend fetches raster tiles from the backend and renders them on the map

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- A [Cloudflare R2](https://developers.cloudflare.com/r2/) bucket with COGs already ingested (see [Ingestion](#ingestion))
- Python ≥ 3.13 (for running ingestion locally)

---

## Getting Started

### 1. Configure environment variables

Create a `.env` file in the project root:

```env
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
R2_S3_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
R2_BUCKET=your_bucket_name
```

### 2. Run the stack

```bash
# Production
docker compose up -d

# Development (frontend hot-reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

The frontend is available at **http://localhost:5326** and the backend API at **http://localhost:8000**.

---

## Ingestion

The ingestion pipeline downloads DTM data and produces COGs ready for serving.

### Setup

```bash
cd ingestion
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Run

```bash
python data_ingestion.py
```

This will:
1. Query the HRDEM STAC API for 1m DTM tiles covering the AOI defined in `data/aoi/`
2. Reproject each tile to EPSG:3857 at 1m/px
3. Compute **slope** and **hillshade relief** rasters
4. Write Cloud-Optimized GeoTIFFs with ZSTD compression and overview pyramids
5. Upload the COGs to the configured R2 bucket

### Tests

```bash
cd ingestion
pytest                          # unit tests only
pytest -m integration           # includes live STAC API calls
```

---

## Backend API

The FastAPI backend exposes a TiTiler mosaic router:

| Endpoint | Description |
|---|---|
| `GET /mosaicjson/tiles/{z}/{x}/{y}` | Raster tile (PNG/WebP) |
| `GET /mosaicjson/tilejson.json` | TileJSON 3.0 metadata |
| `GET /mosaicjson/point/{lon},{lat}` | Pixel value at a coordinate |
| `GET /relief/packing` | `scale_factor` / `add_offset` metadata |

Interactive docs available at **http://localhost:8000/docs**.

---

## Frontend Tools

| Tool | Description |
|---|---|
| **Get Height** | Click any point on the map to query its elevation |
| **Distance Measure** | Click a series of points to measure path distance |
| **Location Search** | Search for a place name and fly to it |
| **WMS Layers** | Toggle DTM, slope, and hillshade WMS overlays |
| **Mosaic Controls** | Adjust opacity and rendering of the COG mosaic layer |

---

## Project Structure

```
RouteRadar/
├── backend/                # FastAPI + TiTiler tile server
│   ├── main.py             # App startup, mosaic build, R2 connection
│   └── routers.py          # Mosaic tile/tilejson endpoints
├── frontend/               # Vite + MapLibre GL web app
│   └── src/
│       ├── map.js          # Map init, AOI bounds, layer management
│       ├── config/         # Layer style defaults
│       ├── tools/          # Map interaction tools (measure, locate)
│       └── ui/             # UI controls (height query, WMS toggles, search)
├── ingestion/              # DTM download and COG generation pipeline
│   ├── data_ingestion.py   # DTMIngestor class
│   └── tests/              # Unit and integration tests
├── experiments/            # Jupyter notebooks for exploratory analysis
├── docker-compose.yml      # Production stack
└── docker-compose.dev.yml  # Dev overrides (hot-reload)
```

---

## Contributing

This project follows a [GitFlow](https://nvie.com/posts/a-successful-git-branching-model/) branching strategy:

- `main` — stable, production-ready code only (PRs required)
- `develop` — integration branch for ongoing work
- `feature/<name>` — branch off `develop` for new features
- `hotfix/<name>` — branch off `main` for urgent fixes

Please open a pull request against `develop` for all new work.


