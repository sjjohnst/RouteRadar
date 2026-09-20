import { buildReliefTileUrl } from '../layers/tileUrls.js';
import { layerDefaults } from '../config/layerDefaults.js';
import { initLayerControls } from './layerControls.js';
import { initReliefColorbar, updateReliefColorbar } from './reliefColorbar.js';

export function setupReliefControls(map) {
    const { id: sourceId, layerId } = layerDefaults.relief;

    initLayerControls(map, {
        layerId,
        toggleId: 'toggle-relief',
        opacityId: 'relief-opacity',
        opacityValueId: 'relief-opacity-value',
    });

    // Relief alone also carries a display range, which drives both the tile
    // URL and the colorbar the user reads it off.
    const vminInput = document.getElementById('relief-vmin');
    const vmaxInput = document.getElementById('relief-vmax');
    const applyBtn = document.getElementById('relief-apply-scale');

    // Current bounds — initialised from layerDefaults
    let vmin = layerDefaults.relief.vminMetres;
    let vmax = layerDefaults.relief.vmaxMetres;

    // Draw the colorbar once on load; it is always visible thereafter.
    initReliefColorbar(vmin, vmax);

    async function updateReliefSource() {
        const newUrl = await buildReliefTileUrl(vmin, vmax);
        const source = map.getSource(sourceId);
        if (source && typeof source.setTiles === 'function') {
            source.setTiles([newUrl]);
        }
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
