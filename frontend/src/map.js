import maplibregl from 'maplibre-gl';
import { layerDefaults } from './config/layerDefaults.js';
import 'maplibre-gl/dist/maplibre-gl.css';
import { BACKEND_URL, QUEBEC_IMAGERY_URL, QUEBEC_PUBLIC_LAND_WMS_URL } from './config/api.js';

// Shared layer/source identifiers so UI and tools stay in sync
export const HRDEM_RELIEF_SOURCE_ID = 'hrdem-relief';
export const HRDEM_RELIEF_LAYER_ID = 'hrdem-relief-layer';
export const QUEBEC_PUBLIC_LAND_SOURCE_ID = 'quebec-public-land';
export const QUEBEC_PUBLIC_LAND_LAYER_ID = 'quebec-public-land-layer';

// Load AOI bounds from a GeoJSON file and apply them
// as maxBounds (and initial view) for versatility.
export async function applyAoiFromGeojson(
    map,
    url = '/aoi/laurentides.geojson',
    options = { fit: true, padding: 40 }
) {
    try {
        const res = await fetch(url);
        if (!res.ok) {
            throw new Error(`Failed to load AOI GeoJSON: ${res.status}`);
        }
        const geojson = await res.json();
        const bbox = computeGeojsonBbox(geojson);
        if (!bbox) {
            return;
        }

        const [minLng, minLat, maxLng, maxLat] = bbox;
        const bounds = [
            [minLng, minLat],
            [maxLng, maxLat]
        ];

        map.setMaxBounds(bounds);

        if (options.fit) {
            map.fitBounds(bounds, { padding: options.padding });
        }
    } catch (err) {
        console.error('Error applying AOI from GeoJSON', err);
    }
}

function computeGeojsonBbox(geojson) {
    if (!geojson) return null;

    const coords = [];

    const collect = (g) => {
        if (!g) return;
        const type = g.type;
        const c = g.coordinates;

        switch (type) {
            case 'Point':
                coords.push(c);
                break;
            case 'MultiPoint':
            case 'LineString':
                c.forEach((pt) => coords.push(pt));
                break;
            case 'MultiLineString':
            case 'Polygon':
                c.forEach((line) => line.forEach((pt) => coords.push(pt)));
                break;
            case 'MultiPolygon':
                c.forEach((poly) =>
                    poly.forEach((line) => line.forEach((pt) => coords.push(pt)))
                );
                break;
            case 'GeometryCollection':
                g.geometries.forEach(collect);
                break;
            default:
                break;
        }
    };

    if (geojson.type === 'Feature') {
        collect(geojson.geometry);
    } else if (geojson.type === 'FeatureCollection') {
        geojson.features.forEach((f) => collect(f.geometry));
    } else if (geojson.type && geojson.coordinates) {
        collect(geojson);
    }

    if (!coords.length) return null;

    let minLng = coords[0][0];
    let minLat = coords[0][1];
    let maxLng = coords[0][0];
    let maxLat = coords[0][1];

    for (const [lng, lat] of coords) {
        if (lng < minLng) minLng = lng;
        if (lng > maxLng) maxLng = lng;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
    }

    return [minLng, minLat, maxLng, maxLat];
}

// Build Quebec Public Land (PATP) WMS URL — routed through local proxy to avoid CORS
export function buildQuebecPublicLandWmsUrl() {    
    const base = import.meta.env.PROD
        ? QUEBEC_PUBLIC_LAND_WMS_URL
        : "/patp-wms";
    return (
        base +
        "?SERVICE=WMS" +
        "&VERSION=1.3.0" +
        "&REQUEST=GetMap" +
        "&LAYERS=Affectations surfaciques" +
        "&STYLES=" +
        "&FORMAT=image/png" +
        "&TRANSPARENT=TRUE" +
        "&CRS=EPSG:3857" +
        "&WIDTH=256&HEIGHT=256" +
        "&BBOX={bbox-epsg-3857}"
    );
}
// Default relief rendering parameters
export const DEFAULT_RELIEF_COLORMAP = 'cividis';

/**
 * Fetch scale_factor and add_offset from the backend, then build a
 * TiTiler relief tile URL with rescale expressed in raw DN units.
 *
 * @param {number} vminMetres  - low end of display range in metres
 * @param {number} vmaxMetres  - high end of display range in metres
 * @param {string} colormap    - colormap name passed to TiTiler
 * @returns {Promise<string>}  - tile URL template with {z}/{x}/{y}
 */
export async function buildReliefTileUrl(
    vminMetres = layerDefaults.relief.vminMetres,
    vmaxMetres = layerDefaults.relief.vmaxMetres,
    colormap   = layerDefaults.relief.colormap,
) {
    let scaleFactor = 0.01;  // fallback matches ingestion default
    let addOffset   = 0.0;
    try {
        const res = await fetch(`${BACKEND_URL}/relief/packing`);
        if (res.ok) {
            const meta = await res.json();
            scaleFactor = meta.scale_factor;
            addOffset   = meta.add_offset;
        }
    } catch (err) {
        console.warn('Could not fetch relief packing metadata, using defaults:', err);
    }

    // Convert physical metres → packed DN
    const vminDN = (vminMetres - addOffset) / scaleFactor;
    const vmaxDN = (vmaxMetres - addOffset) / scaleFactor;

    const params = new URLSearchParams({
        rescale:      `${vminDN},${vmaxDN}`,
        colormap_name: colormap,
    });
    // Use the "tiler://" custom protocol so MapLibre routes these tiles through
    // registerTilerProtocol(), which retries 503s per-tile without touching the
    // cache of already-loaded tiles (avoids blurry zoom-out fallback on retry).
    const httpsUrl = `${BACKEND_URL}/mosaicjson/tiles/WebMercatorQuad/{z}/{x}/{y}?${params.toString()}`;
    return httpsUrl.replace(/^https:\/\//, 'tiler://');
}

export async function initMap() {
    const quebecImageryUrl = QUEBEC_IMAGERY_URL;
    const cartoLabelsUrl = "https://maps-cartes.services.geo.ca/server2_serveur2/rest/services/BaseMaps/CBMT_TXT_3857/MapServer/WMTS/tile/1.0.0/BaseMaps_CBMT_TXT_3857/default/default028mm/{z}/{y}/{x}.png";

    // Build the relief tile URL (async — fetches packing metadata from backend)
    const reliefUrl = await buildReliefTileUrl();

    // Quebec Public Land WMS URL
    const quebecPublicLandUrl = buildQuebecPublicLandWmsUrl();

    const map = new maplibregl.Map({
        container: 'map',
        // Lock the map to a top-down, north-up view
        pitch: 0,
        bearing: 0,
        dragRotate: false,
        pitchWithRotate: false,
        touchZoomRotate: false,
        // Cap concurrent tile fetches to stay well under the Lambda account
        maxParallelImageRequests: 4,
        style: {
            version: 8,
            sources: {
                'quebec-imagery': {
                    type: 'raster',
                    tiles: [quebecImageryUrl],
                    tileSize: 256,
                    attribution: 'Imagery: <a href="https://mrnf.gouv.qc.ca/repertoire-geographique/vue-aerienne-quebec-imagerie-continue/" target="_blank">Ministère des Ressources naturelles et des Forêts</a>'
                },
                [HRDEM_RELIEF_SOURCE_ID]: {
                    type: 'raster',
                    tiles: [reliefUrl],
                    tileSize: 256,
                    attribution: 'Relief derived from: <a href="https://ouvert.canada.ca/data/dataset/957782bf-847c-4644-a757-e383c0057995" target="_blank">Government of Canada</a>'
                },
                'map-labels': {
                    type: 'raster',
                    tiles: [cartoLabelsUrl],
                    tileSize: 256,
                    attribution: 'Labels: <a href="https://open.canada.ca/data/en/dataset/7dd22445-fa7f-49f4-ae9a-2cf70af8f875" target="_blank">Government of Canada</a>'
                },
                [QUEBEC_PUBLIC_LAND_SOURCE_ID]: {
                    type: 'raster',
                    tiles: [quebecPublicLandUrl],
                    tileSize: 256,
                    attribution: 'Public Land: <a href="https://www.donneesquebec.ca/recherche/dataset/plans-d-affectation-du-territoire-public" target="_blank">Ministère des Ressources naturelles et des Forêts</a>'
                }
            },
            layers: [
                { id: 'base-imagery', type: 'raster', source: 'quebec-imagery' },
                { id: HRDEM_RELIEF_LAYER_ID, type: 'raster', source: HRDEM_RELIEF_SOURCE_ID, paint: { 'raster-opacity': layerDefaults.relief.opacity }, layout: { visibility: layerDefaults.relief.visible ? 'visible' : 'none' } },
                { id: QUEBEC_PUBLIC_LAND_LAYER_ID, type: 'raster', source: QUEBEC_PUBLIC_LAND_SOURCE_ID, paint: { 'raster-opacity': layerDefaults.quebecPublicLand.opacity }, layout: { visibility: layerDefaults.quebecPublicLand.visible ? 'visible' : 'none' } },
                { id: 'labels-layer', type: 'raster', source: 'map-labels' },
            ]
        },
        center: [-74.19, 46.03],
        zoom: 8
    });

    // Remove the default attribution control if present
    map.removeControl(map._controls.find(c => c instanceof maplibregl.AttributionControl));

    // Add attribution control with custom prefix and compact styling
    const attributionControl = new maplibregl.AttributionControl({
        compact: true,
        customAttribution: '© RouteRadar'
    });
    map.addControl(attributionControl, 'bottom-right');

    // Add a metric scale bar in the bottom-left corner for better visibility
    const scale = new maplibregl.ScaleControl({ maxWidth: 260, unit: 'metric' });
    map.addControl(scale, 'bottom-left');

    return map;
}

/**
 * Register a custom protocol "tiler://" that wraps backend tile fetches with
 * exponential-backoff retry on HTTP 503 (Lambda cold-start burst throttle).
 *
 * MapLibre's addProtocol intercepts the fetch for a single tile URL and lets
 * us resolve/reject it ourselves — so only the specific failing tile is retried.
 * All other already-loaded tiles stay in cache untouched, preventing the
 * blurry-fallback problem caused by clearing the entire source cache.
 *
 * Call this once before initMap(), then use buildTilerUrl() to prefix tile
 * template URLs with "tiler://" instead of "https://".
 *
 * @param {typeof import('maplibre-gl')} maplibregl
 */
export function registerTilerProtocol(maplibregl) {
    maplibregl.addProtocol('tiler', async (params, abortController) => {
        // Strip the custom scheme: "tiler://foo.com/..." → "https://foo.com/..."
        const url = params.url.replace(/^tiler:\/\//, 'https://');

        let delay = 400; // ms — initial back-off
        const maxRetries = 4;

        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            if (abortController.signal.aborted) {
                throw new DOMException('Tile fetch aborted', 'AbortError');
            }
            const res = await fetch(url, { signal: abortController.signal });
            if (res.status !== 503 || attempt === maxRetries) {
                if (!res.ok) throw new Error(`Tile fetch failed: ${res.status}`);
                const data = await res.arrayBuffer();
                return { data };
            }
            // 503 — wait with jitter before retrying
            await new Promise((r) =>
                setTimeout(r, delay + Math.random() * delay)
            );
            delay = Math.min(delay * 2, 3000);
        }
    });
}