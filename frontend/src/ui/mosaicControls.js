import { buildReliefTileUrl, HRDEM_RELIEF_SOURCE_ID, HRDEM_RELIEF_LAYER_ID } from '../map.js';
import { layerDefaults } from '../config/layerDefaults.js';
import { initReliefColorbar, updateReliefColorbar, showReliefColorbar } from './reliefColorbar.js';

export async function setupReliefControls(map) {
    const reliefToggle        = document.getElementById('toggle-relief');
    const reliefOpacitySlider = document.getElementById('relief-opacity');
    const reliefOpacityValue  = document.getElementById('relief-opacity-value');
    const vminInput           = document.getElementById('relief-vmin');
    const vmaxInput           = document.getElementById('relief-vmax');
    const applyBtn            = document.getElementById('relief-apply-scale');

    // Current bounds — initialised from layerDefaults
    let vmin = layerDefaults.relief.vminMetres;
    let vmax = layerDefaults.relief.vmaxMetres;

    // Draw the colorbar once on load and show it if the layer is visible
    initReliefColorbar(vmin, vmax);
    showReliefColorbar(reliefToggle && reliefToggle.checked);

    async function updateReliefSource() {
        const newUrl = await buildReliefTileUrl(vmin, vmax);
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
            showReliefColorbar(reliefToggle.checked);
        });
    }

    if (reliefOpacitySlider && reliefOpacityValue) {
        // Set initial value to 3 decimals
        reliefOpacityValue.textContent = parseFloat(reliefOpacitySlider.value).toFixed(2);
        reliefOpacitySlider.addEventListener('input', () => {
            const value = parseFloat(reliefOpacitySlider.value);
            reliefOpacityValue.textContent = value.toFixed(2);
            if (map.getLayer(HRDEM_RELIEF_LAYER_ID)) {
                map.setPaintProperty(HRDEM_RELIEF_LAYER_ID, 'raster-opacity', value);
            }
        });
    }

    function handleRescaleApply() {
        const newVmin = parseFloat(vminInput.value);
        const newVmax = parseFloat(vmaxInput.value);
        if (!Number.isFinite(newVmin) || !Number.isFinite(newVmax) || newVmin >= newVmax) {
            // Optionally: add error styling or tooltip
            return;
        }
        vmin = newVmin;
        vmax = newVmax;
        updateReliefColorbar(vmin, vmax);
        updateReliefSource();
    }
    if (applyBtn) {
        applyBtn.addEventListener('click', handleRescaleApply);
    }
}
