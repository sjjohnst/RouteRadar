import { layerDefaults } from '../config/layerDefaults.js';

export function setupQuebecPublicLandControls(map) {
    const { layerId } = layerDefaults.quebecPublicLand;
    const toggle = document.getElementById('toggle-quebec-public-land');
    const opacitySlider = document.getElementById('quebec-public-land-opacity');
    const opacityValue = document.getElementById('quebec-public-land-opacity-value');

    // --- Visibility toggle ---
    if (toggle) {
        toggle.addEventListener('change', () => {
            if (map.getLayer(layerId)) {
                map.setLayoutProperty(
                    layerId,
                    'visibility',
                    toggle.checked ? 'visible' : 'none'
                );
            }
        });
    }

    // --- Opacity slider ---
    if (opacitySlider && opacityValue) {
        // Set initial value to 3 decimals
        opacityValue.textContent = parseFloat(opacitySlider.value).toFixed(2);
        opacitySlider.addEventListener('input', () => {
            const value = parseFloat(opacitySlider.value);
            opacityValue.textContent = value.toFixed(2);
            if (map.getLayer(layerId)) {
                map.setPaintProperty(layerId, 'raster-opacity', value);
            }
        });
    }
}
