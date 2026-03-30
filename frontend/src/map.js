import maplibregl from 'maplibre-gl';
import { layerDefaults } from './config/layerDefaults.js';
import 'maplibre-gl/dist/maplibre-gl.css';
import { BACKEND_URL, QUEBEC_IMAGERY_URL, QUEBEC_PUBLIC_LAND_WMS_URL } from './config/api.js';

// Shared layer/source identifiers so UI and tools stay in sync
export const HRDEM_RELIEF_SOURCE_ID = 'hrdem-relief';
export const HRDEM_RELIEF_LAYER_ID = 'hrdem-relief-layer';
export const HRDEM_WMS_DTM_SOURCE_ID = 'hrdem-wms-dtm';
export const HRDEM_WMS_DTM_LAYER_ID = 'hrdem-wms-dtm-layer';
export const HRDEM_WMS_SLOPE_SOURCE_ID = 'hrdem-wms-slope';
export const HRDEM_WMS_SLOPE_LAYER_ID = 'hrdem-wms-slope-layer';
export const HRDEM_WMS_HILLSHADE_SOURCE_ID = 'hrdem-wms-hillshade';
export const HRDEM_WMS_HILLSHADE_LAYER_ID = 'hrdem-wms-hillshade-layer';
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

// Reusable function to build HRDEM WMS URL
export function buildHRDEMWmsUrl(layer = 'dtm', style = '') {
    let url = "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic?SERVICE=WMS" +
        "&VERSION=1.3.0" +
        "&REQUEST=GetMap" +
        `&LAYERS=${layer}` +
        (style ? `&STYLES=${style}` : '') +
        "&FORMAT=image/png" +
        "&TRANSPARENT=FALSE" +
        "&CRS=EPSG:3857" +
        "&WIDTH=256&HEIGHT=256" +
        "&BBOX={bbox-epsg-3857}";
    return url;
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
    return `${BACKEND_URL}/mosaicjson/tiles/WebMercatorQuad/{z}/{x}/{y}?${params.toString()}`;
}

export async function initMap() {
    const quebecImageryUrl = QUEBEC_IMAGERY_URL;
    const cartoLabelsUrl = "https://maps-cartes.services.geo.ca/server2_serveur2/rest/services/BaseMaps/CBMT_TXT_3857/MapServer/WMTS/tile/1.0.0/BaseMaps_CBMT_TXT_3857/default/default028mm/{z}/{y}/{x}.png";

    // Build the relief tile URL (async — fetches packing metadata from backend)
    const reliefUrl = await buildReliefTileUrl();
    // HRDEM WMS URLs
    const hrdemWmsDtmUrl = buildHRDEMWmsUrl('dtm', layerDefaults.dtm.style);
    const hrdemWmsSlopeUrl = buildHRDEMWmsUrl('dtm-slope', layerDefaults.slope.style);
    const hrdemWmsHillshadeUrl = buildHRDEMWmsUrl('dtm-hillshade', layerDefaults.hillshade.style);
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
        style: {
            version: 8,
            sources: {
                'quebec-imagery': { type: 'raster', tiles: [quebecImageryUrl], tileSize: 256 },
                'map-labels': { type: 'raster', tiles: [cartoLabelsUrl], tileSize: 256 },
                // Relief COG mosaic source
                [HRDEM_RELIEF_SOURCE_ID]: {
                    type: 'raster',
                    tiles: [reliefUrl],
                    tileSize: 256,
                },
                // HRDEM WMS sources
                [HRDEM_WMS_DTM_SOURCE_ID]: {
                    type: 'raster',
                    tiles: [hrdemWmsDtmUrl],
                    tileSize: 256,
                },
                [HRDEM_WMS_SLOPE_SOURCE_ID]: {
                    type: 'raster',
                    tiles: [hrdemWmsSlopeUrl],
                    tileSize: 256,
                },
                [HRDEM_WMS_HILLSHADE_SOURCE_ID]: {
                    type: 'raster',
                    tiles: [hrdemWmsHillshadeUrl],
                    tileSize: 256,
                },
                [QUEBEC_PUBLIC_LAND_SOURCE_ID]: {
                    type: 'raster',
                    tiles: [quebecPublicLandUrl],
                    tileSize: 256,
                }
            },
            layers: [
                { id: 'base-imagery', type: 'raster', source: 'quebec-imagery' },
                { id: HRDEM_RELIEF_LAYER_ID, type: 'raster', source: HRDEM_RELIEF_SOURCE_ID, paint: { 'raster-opacity': layerDefaults.relief.opacity }, layout: { visibility: layerDefaults.relief.visible ? 'visible' : 'none' } },
                { id: HRDEM_WMS_DTM_LAYER_ID, type: 'raster', source: HRDEM_WMS_DTM_SOURCE_ID, paint: { 'raster-opacity': layerDefaults.dtm.opacity }, layout: { visibility: layerDefaults.dtm.visible ? 'visible' : 'none' } },
                { id: HRDEM_WMS_SLOPE_LAYER_ID, type: 'raster', source: HRDEM_WMS_SLOPE_SOURCE_ID, paint: { 'raster-opacity': layerDefaults.slope.opacity }, layout: { visibility: layerDefaults.slope.visible ? 'visible' : 'none' } },
                { id: HRDEM_WMS_HILLSHADE_LAYER_ID, type: 'raster', source: HRDEM_WMS_HILLSHADE_SOURCE_ID, paint: { 'raster-opacity': layerDefaults.hillshade.opacity }, layout: { visibility: layerDefaults.hillshade.visible ? 'visible' : 'none' } },
                { id: QUEBEC_PUBLIC_LAND_LAYER_ID, type: 'raster', source: QUEBEC_PUBLIC_LAND_SOURCE_ID, paint: { 'raster-opacity': layerDefaults.quebecPublicLand.opacity }, layout: { visibility: layerDefaults.quebecPublicLand.visible ? 'visible' : 'none' } },
                { id: 'labels-layer', type: 'raster', source: 'map-labels' },
            ]
        },
        center: [-74.19, 46.03],
        zoom: 8
    });

    // Add a metric scale bar in the bottom-right corner
    const scale = new maplibregl.ScaleControl({ maxWidth: 150, unit: 'metric' });
    map.addControl(scale, 'bottom-right');

    return map;
}