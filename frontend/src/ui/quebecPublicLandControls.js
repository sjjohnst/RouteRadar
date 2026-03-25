import { QUEBEC_PUBLIC_LAND_LAYER_ID } from '../map.js';

export function setupQuebecPublicLandControls(map) {
    const toggle = document.getElementById('toggle-quebec-public-land');
    const opacitySlider = document.getElementById('quebec-public-land-opacity');
    const opacityValue = document.getElementById('quebec-public-land-opacity-value');

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
}
