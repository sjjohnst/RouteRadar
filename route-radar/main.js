import './style.css'
import maplibregl from 'maplibre-gl';
import { initMap, buildHRDEMWmsUrl } from './src/map.js'

// Initialize the map when the page loads
const map = initMap();

// --- HRDEM Layer Controls ---
const toggle = document.getElementById('toggle-hrdem');
const opacitySlider = document.getElementById('hrdem-opacity');
const opacityValue = document.getElementById('opacity-value');
const slopeMinInput = document.getElementById('hrdem-slope-min');
const slopeMaxInput = document.getElementById('hrdem-slope-max');

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
