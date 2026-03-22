import maplibregl from 'maplibre-gl';
import { QUEBEC_PUBLIC_LAND_LAYER_ID } from '../map.js';

// Routed through our own proxy (vite.config.js / nginx.conf) to avoid CORS
const WMS_BASE = '/patp-wms';
const WMS_LAYER = 'Affectations surfaciques';
// Tile size used when computing I,J pixel coordinates for GetFeatureInfo
const GFI_SIZE = 256;

/**
 * Build a WMS GetFeatureInfo URL for the given map click.
 * We use the map's current viewport as the BBOX and derive the pixel
 * offset (I, J) from where the user clicked within it.
 */
function buildGetFeatureInfoUrl(map, lngLat) {
    const canvas = map.getCanvas();
    const W = canvas.width;
    const H = canvas.height;

    // Current viewport bounds in EPSG:3857 (Web Mercator)
    const bounds = map.getBounds();
    const sw = maplibregl.MercatorCoordinate.fromLngLat(bounds.getSouthWest());
    const ne = maplibregl.MercatorCoordinate.fromLngLat(bounds.getNorthEast());

    // MercatorCoordinate is in 0-1 world units; convert to metres by multiplying
    // by the circumference of the Earth at the equator in metres for EPSG:3857.
    const EARTH_CIRC = 2 * Math.PI * 6378137;
    const minX = sw.x * EARTH_CIRC - Math.PI * 6378137;
    const maxX = ne.x * EARTH_CIRC - Math.PI * 6378137;
    // Y is inverted in Mercator (north = smaller world unit)
    const maxY = (1 - sw.y) * EARTH_CIRC - Math.PI * 6378137;
    const minY = (1 - ne.y) * EARTH_CIRC - Math.PI * 6378137;

    // Pixel coordinates of the click relative to the canvas
    const point = map.project(lngLat);
    const I = Math.round((point.x / W) * GFI_SIZE);
    const J = Math.round((point.y / H) * GFI_SIZE);

    const params = new URLSearchParams({
        SERVICE: 'WMS',
        VERSION: '1.3.0',
        REQUEST: 'GetFeatureInfo',
        LAYERS: WMS_LAYER,
        QUERY_LAYERS: WMS_LAYER,
        INFO_FORMAT: 'application/geojson',
        FEATURE_COUNT: 5,
        CRS: 'EPSG:3857',
        WIDTH: GFI_SIZE,
        HEIGHT: GFI_SIZE,
        BBOX: `${minX},${minY},${maxX},${maxY}`,
        I,
        J,
    });
    return `${WMS_BASE}?${params.toString()}`;
}

/** Format a GeoJSON feature's properties into HTML for the popup. */
function featureToHtml(feature) {
    const props = feature.properties || {};
    const rows = Object.entries(props)
        .filter(([, v]) => v !== null && v !== '' && v !== undefined)
        .map(([k, v]) => `<tr><td><strong>${k}</strong></td><td>${v}</td></tr>`)
        .join('');
    return rows
        ? `<table style="font-size:0.8em;border-collapse:collapse">${rows}</table>`
        : '<em>No attributes</em>';
}

export function setupQuebecPublicLandControls(map) {
    const toggle = document.getElementById('toggle-quebec-public-land');
    const opacitySlider = document.getElementById('quebec-public-land-opacity');
    const opacityValue = document.getElementById('quebec-public-land-opacity-value');
    const identifyBtn = document.getElementById('tool-quebec-public-land-identify');
    const output = document.getElementById('quebec-public-land-output');

    // --- Visibility toggle ---
    if (toggle) {
        toggle.addEventListener('change', () => {
            if (map.getLayer(QUEBEC_PUBLIC_LAND_LAYER_ID)) {
                map.setLayoutProperty(
                    QUEBEC_PUBLIC_LAND_LAYER_ID,
                    'visibility',
                    toggle.checked ? 'visible' : 'none'
                );
            }
        });
    }

    // --- Opacity slider ---
    if (opacitySlider && opacityValue) {
        opacitySlider.addEventListener('input', () => {
            const value = parseFloat(opacitySlider.value);
            opacityValue.textContent = value.toFixed(2);
            if (map.getLayer(QUEBEC_PUBLIC_LAND_LAYER_ID)) {
                map.setPaintProperty(QUEBEC_PUBLIC_LAND_LAYER_ID, 'raster-opacity', value);
            }
        });
    }

    // --- Identify tool ---
    if (!identifyBtn || !output) return;

    let active = false;
    let popup = null;
    let clickHandler = null;

    const deactivate = () => {
        active = false;
        identifyBtn.classList.remove('active-tool');
        map.getCanvas().style.cursor = '';
        output.textContent = '';
        if (clickHandler) map.off('click', clickHandler);
        clickHandler = null;
    };

    identifyBtn.addEventListener('click', () => {
        if (active) {
            deactivate();
            return;
        }
        active = true;
        identifyBtn.classList.add('active-tool');
        map.getCanvas().style.cursor = 'crosshair';
        output.textContent = 'Click on a public land feature…';

        clickHandler = async (e) => {
            output.textContent = 'Querying…';
            if (popup) { popup.remove(); popup = null; }

            try {
                const url = buildGetFeatureInfoUrl(map, e.lngLat);
                const res = await fetch(url);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const geojson = await res.json();
                const features = geojson.features ?? [];

                if (!features.length) {
                    output.textContent = 'No public land feature at this location.';
                    return;
                }

                // Show the first feature's attributes in a popup
                const html = featureToHtml(features[0]);
                popup = new maplibregl.Popup({ maxWidth: '320px' })
                    .setLngLat(e.lngLat)
                    .setHTML(html)
                    .addTo(map);

                // Also summarise in the panel
                const name = features[0].properties?.NOM_AFFECT
                    ?? features[0].properties?.NOM
                    ?? 'Feature';
                output.textContent = `${name}${features.length > 1 ? ` (+${features.length - 1} more)` : ''}`;
            } catch (err) {
                output.textContent = 'Error querying feature info.';
                console.error('GetFeatureInfo error:', err);
            }
        };

        map.on('click', clickHandler);
    });
}
