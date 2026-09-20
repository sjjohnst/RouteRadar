import maplibregl from 'maplibre-gl';
import { layerDefaults } from './config/layerDefaults.js';
import { AOI_BOUNDS } from './aoi.js';
import { buildReliefTileUrl, publicLandWmsUrl } from './layers/tileUrls.js';
import { registerTilerProtocol } from './tilerProtocol.js';
import 'maplibre-gl/dist/maplibre-gl.css';
import { QUEBEC_IMAGERY_URL } from './config/api.js';

export async function initMap() {
    // Before the style names any tiler:// url, so MapLibre can resolve them.
    registerTilerProtocol(maplibregl);

    const { relief, quebecPublicLand } = layerDefaults;
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
        // Declined here so we can add our own below, prefixed and compact
        attributionControl: false,
        style: {
            version: 8,
            sources: {
                'quebec-imagery': {
                    type: 'raster',
                    tiles: [quebecImageryUrl],
                    tileSize: 256,
                    attribution: 'Imagery: <a href="https://mrnf.gouv.qc.ca/repertoire-geographique/vue-aerienne-quebec-imagerie-continue/" target="_blank">Ministère des Ressources naturelles et des Forêts</a>'
                },
                [relief.id]: {
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
                [quebecPublicLand.id]: {
                    type: 'raster',
                    tiles: [quebecPublicLandUrl],
                    tileSize: 256,
                    attribution: 'Public Land: <a href="https://www.donneesquebec.ca/recherche/dataset/plans-d-affectation-du-territoire-public" target="_blank">Ministère des Ressources naturelles et des Forêts</a>'
                }
            },
            layers: [
                { id: 'base-imagery', type: 'raster', source: 'quebec-imagery' },
                { id: relief.layerId, type: 'raster', source: relief.id, paint: { 'raster-opacity': relief.opacity }, layout: { visibility: relief.visible ? 'visible' : 'none' } },
                { id: quebecPublicLand.layerId, type: 'raster', source: quebecPublicLand.id, paint: { 'raster-opacity': quebecPublicLand.opacity }, layout: { visibility: quebecPublicLand.visible ? 'visible' : 'none' } },
                { id: 'labels-layer', type: 'raster', source: 'map-labels' },
            ]
        },
        // Open on the AOI and lock the camera to it. `bounds` supersedes
        // center/zoom, so the first paint is already framed correctly.
        bounds: AOI_BOUNDS,
        fitBoundsOptions: { padding: 40 },
        maxBounds: AOI_BOUNDS
    });

    map.addControl(
        new maplibregl.AttributionControl({ compact: true, customAttribution: '© RouteRadar' }),
        'bottom-right'
    );
    // `compact` means collapsible, not collapsed — MapLibre adds compact-show on
    // add and only drops it on the first drag. Start folded to the ⓘ instead.
    map.getContainer()
        .querySelector('.maplibregl-ctrl-attrib')
        ?.classList.remove('maplibregl-compact-show');

    // Add a metric scale bar in the bottom-left corner for better visibility
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 260, unit: 'metric' }), 'bottom-left');

    return map;
}