import { buildReliefTileUrl, HRDEM_RELIEF_SOURCE_ID, HRDEM_RELIEF_LAYER_ID } from '../map.js';

export async function setupReliefControls(map) {
    const reliefToggle = document.getElementById('toggle-relief');
    const reliefOpacitySlider = document.getElementById('relief-opacity');
    const reliefOpacityValue = document.getElementById('relief-opacity-value');

    async function updateReliefSource() {
        const newUrl = await buildReliefTileUrl();

        const source = map.getSource(HRDEM_RELIEF_SOURCE_ID);
        if (source && typeof source.setTiles === 'function') {
            source.setTiles([newUrl]);
        }
    }

    if (reliefToggle) {
        reliefToggle.addEventListener('change', () => {
            if (map.getLayer(HRDEM_RELIEF_LAYER_ID)) {
                map.setLayoutProperty(
                    HRDEM_RELIEF_LAYER_ID,
                    'visibility',
                    reliefToggle.checked ? 'visible' : 'none'
                );
            }
        });
    }

    if (reliefOpacitySlider && reliefOpacityValue) {
        reliefOpacitySlider.addEventListener('input', () => {
            const value = parseFloat(reliefOpacitySlider.value);
            reliefOpacityValue.textContent = value.toFixed(2);
            if (map.getLayer(HRDEM_RELIEF_LAYER_ID)) {
                map.setPaintProperty(HRDEM_RELIEF_LAYER_ID, 'raster-opacity', value);
            }
        });
    }
}
