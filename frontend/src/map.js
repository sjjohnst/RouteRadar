import maplibregl from 'maplibre-gl';
import { layerDefaults } from './config/layerDefaults.js';
import { AOI_BOUNDS } from './aoi.js';
import { buildReliefTileUrl, publicLandWmsUrl } from './layers/tileUrls.js';
import 'maplibre-gl/dist/maplibre-gl.css';
import { QUEBEC_IMAGERY_URL } from './config/api.js';

// Shared layer/source identifiers so UI and tools stay in sync
export const HRDEM_RELIEF_SOURCE_ID = 'hrdem-relief';
export const HRDEM_RELIEF_LAYER_ID = 'hrdem-relief-layer';
export const QUEBEC_PUBLIC_LAND_SOURCE_ID = 'quebec-public-land';
export const QUEBEC_PUBLIC_LAND_LAYER_ID = 'quebec-public-land-layer';

export async function initMap() {
    const quebecImageryUrl = QUEBEC_IMAGERY_URL;
    const cartoLabelsUrl = "https://maps-cartes.services.geo.ca/server2_serveur2/rest/services/BaseMaps/CBMT_TXT_3857/MapServer/WMTS/tile/1.0.0/BaseMaps_CBMT_TXT_3857/default/default028mm/{z}/{y}/{x}.png";

    // Build the relief tile URL (async — fetches packing metadata from backend)
    const reliefUrl = await buildReliefTileUrl();

    // Quebec Public Land WMS URL
    const quebecPublicLandUrl = publicLandWmsUrl();

    const map = new maplibregl.Map({
        container: 'map',
        // Lock the map to a top-down, north-up view
        pitch: 0,
        bearing: 0,
        dragRotate: false,
        pitchWithRotate: false,
        touchZoomRotate: false,
        // Cap concurrent tile fetches to stay well under the Lambda account
        maxParallelImageRequests: 8,
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
        // Open on the AOI and lock the camera to it. `bounds` supersedes
        // center/zoom, so the first paint is already framed correctly.
        bounds: AOI_BOUNDS,
        fitBoundsOptions: { padding: 40 },
        maxBounds: AOI_BOUNDS
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