# RouteRadar

A geospatial web application for rock climbing route development. RouteRadar ingests high-resolution digital elevation model (HRDEM) data, computes slope and relief rasters, and serves them as interactive map tiles — helping climbers and route developers identify promising terrain features like cliffs and steep faces.

---

## Architecture

```
ingestion/    # Python pipeline: STAC → DTM → COG → Cloudflare R2
backend/      # FastAPI + TiTiler: serves mosaic raster tiles from R2 (AWS Lambda)
frontend/     # Vite + MapLibre GL: interactive map (Cloudflare Pages)
```

**Data flow:**
1. `DTMIngestor` queries the HRDEM STAC API for 1m DTM tiles over the AOI
2. Each tile is reprojected to EPSG:3857, slope/relief computed, and written as a COG
3. COGs are uploaded to a Cloudflare R2 bucket
4. On startup, the backend lists all COGs in R2, builds a MosaicJSON in memory, and serves tiles
5. The frontend fetches raster tiles from the backend and renders them on the map

---

## Quick Start (Local Development)

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- Node.js ≥ 22
- A Cloudflare R2 bucket with COGs already ingested (see [Ingestion](#ingestion))

### 1. Root environment variables

Create `.env` in the project root (gitignored):

```env
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
R2_S3_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
R2_BUCKET=your_bucket_name
```

### 2. Frontend environment variables

Create `frontend/.env.local` (gitignored):

```env
VITE_BACKEND_URL=http://localhost:8000
```

> To develop against the live Lambda instead of a local backend, change this to the API Gateway URL.

### 3. Start the backend

```bash
docker compose up --build
```

The backend (uvicorn, live-reload) starts at **http://localhost:8000**.
Interactive API docs: **http://localhost:8000/docs**

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The app is available at **http://localhost:5173**.

---

## How environment variables work

`VITE_BACKEND_URL` is baked into the JS bundle at build time by Vite. Vite loads env files in this priority order (highest first):

| File | Committed | Used when |
|---|---|---|
| `frontend/.env.local` | No (gitignored) | `npm run dev` — always overrides |
| `frontend/.env.production` | Yes | `npm run build` / `npm run deploy` |

This means:
- **Local dev** always hits `localhost:8000` (from `.env.local`)
- **Cloudflare Pages** always hits the Lambda (from `.env.production`, baked in at build time — no runtime config needed)

---

## Deployment

### Frontend → Cloudflare Pages

```bash
cd frontend && npm run deploy
```

### Backend → AWS Lambda

Build and push the production image to ECR, then apply Terraform:

```bash
cd infra/terraform && terraform apply
```

The production Dockerfile (`backend/Dockerfile`) uses the AWS Lambda Python runtime.
The dev Dockerfile (`backend/Dockerfile.dev`) uses uvicorn — only used by `docker compose`.

---

## Ingestion

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

1. Queries the HRDEM STAC API for 1m DTM tiles covering the AOI in `data/aoi/`
2. Reprojects each tile to EPSG:3857 at 1m/px
3. Computes slope and hillshade relief rasters
4. Writes Cloud-Optimized GeoTIFFs with ZSTD compression and overview pyramids
5. Uploads COGs to the configured R2 bucket

### Tests

```bash
cd ingestion
pytest                    # unit tests only
pytest -m integration     # includes live STAC API calls
```

---

## Backend API

| Endpoint | Description |
|---|---|
| `GET /mosaicjson/tiles/{z}/{x}/{y}` | Raster tile (PNG/WebP) |
| `GET /mosaicjson/tilejson.json` | TileJSON 3.0 metadata |
| `GET /relief/point?lng=&lat=` | Elevation (metres) at a coordinate |
| `GET /relief/packing` | `scale_factor` / `add_offset` metadata |

---

## Frontend Tools

| Tool | Description |
|---|---|
| **Info Tool** | Click any point to query elevation and public land status |
| **Distance Measure** | Click a series of points to measure path distance |
| **Location Search** | Search for a place name and fly to it |
| **WMS Layers** | Toggle DTM, slope, and hillshade WMS overlays |
| **Mosaic Controls** | Adjust opacity and colour scaling of the COG mosaic layer |

---

## Project Structure

```
RouteRadar/
├── .env                    # R2 credentials — gitignored
├── docker-compose.yml      # Backend dev stack (uvicorn, live-reload)
├── backend/
│   ├── Dockerfile          # Production image (AWS Lambda runtime)
│   ├── Dockerfile.dev      # Dev image (uvicorn)
│   ├── main.py
│   ├── routers.py
│   └── state.py
├── frontend/
│   ├── .env.production     # Lambda URL
│   ├── .env.local          # Local backend URL
│   ├── src/
│   │   ├── map.js
│   │   ├── config/
│   │   ├── tools/
│   │   └── ui/
│   └── main.js
├── ingestion/              # DTM download and COG generation pipeline
└── infra/terraform/        # AWS Lambda + API Gateway infrastructure
```

---
