import './style.css'
import { initMap, buildCogTileUrl } from './src/map.js'

// Initialize the map when the page loads
const map = initMap();

// --- HRDEM Layer Controls ---
const toggle = document.getElementById('toggle-hrdem');
const opacitySlider = document.getElementById('hrdem-opacity');
const opacityValue = document.getElementById('opacity-value');

toggle.addEventListener('change', () => {
    map.setLayoutProperty(
        'hrdem-wms-layer',
        'visibility',
        toggle.checked ? 'visible' : 'none'
    );
});

opacitySlider.addEventListener('input', () => {
    const value = parseFloat(opacitySlider.value);
    opacityValue.textContent = value.toFixed(2);
    map.setPaintProperty('hrdem-wms-layer', 'raster-opacity', value);
});

// --- COG Layer Controls ---
const cogToggle = document.getElementById('toggle-cog');
const cogOpacitySlider = document.getElementById('cog-opacity');
const cogOpacityValue = document.getElementById('cog-opacity-value');
const cogColormap = document.getElementById('cog-colormap');
const cogRescale = document.getElementById('cog-rescale');
const cogApplyBtn = document.getElementById('apply-cog-params');


function updateCogSource() {
    const colormap = cogColormap.value;
    const rescale = cogRescale.value;
    const url = buildCogTileUrl({colormap, rescale});
    // Remove and re-add the source to update tiles
    if (map.getLayer('local-cog-layer')) {
        map.removeLayer('local-cog-layer');
    }
    if (map.getSource('local-cog')) {
        map.removeSource('local-cog');
    }
        // Bounds from laurentides.geojson polygon
        // [[-74.30994776313827, 46.07484617926616], [-74.30994776313827, 45.85327435249255], [-74.05654223402449, 45.85327435249255], [-74.05654223402449, 46.07484617926616], [-74.30994776313827, 46.07484617926616]]
        const laurentidesBounds = [
            -74.30994776313827, // minX (west)
            45.85327435249255,  // minY (south)
            -74.05654223402449, // maxX (east)
            46.07484617926616   // maxY (north)
        ];
        map.addSource('local-cog', {
            type: 'raster',
            tiles: [url],
            tileSize: 256,
            bounds: laurentidesBounds
        });
    map.addLayer({
        id: 'local-cog-layer',
        type: 'raster',
        source: 'local-cog',
        paint: { 'raster-opacity': parseFloat(cogOpacitySlider.value) },
    }, 'hrdem-wms-layer');
    // Respect visibility toggle
    map.setLayoutProperty('local-cog-layer', 'visibility', cogToggle.checked ? 'visible' : 'none');
}

cogToggle.addEventListener('change', () => {
    if (map.getLayer('local-cog-layer')) {
        map.setLayoutProperty(
            'local-cog-layer',
            'visibility',
            cogToggle.checked ? 'visible' : 'none'
        );
    }
});

cogOpacitySlider.addEventListener('input', () => {
    const value = parseFloat(cogOpacitySlider.value);
    cogOpacityValue.textContent = value.toFixed(2);
    if (map.getLayer('local-cog-layer')) {
        map.setPaintProperty('local-cog-layer', 'raster-opacity', value);
    }
});

cogApplyBtn.addEventListener('click', () => {
    updateCogSource();
});

// Optionally, update on colormap or rescale enter
cogColormap.addEventListener('change', () => updateCogSource());
cogRescale.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') updateCogSource();
});
