// The checkbox-and-slider pair every raster layer gets in the Layers panel:
// the toggle drives visibility, the slider drives raster-opacity and its own
// readout. Both are guarded on getLayer, because the style may not carry the
// layer yet when a control fires.

/**
 * @param {import('maplibre-gl').Map} map
 * @param {{layerId: string, toggleId: string, opacityId: string, opacityValueId: string}} ids
 */
export function initLayerControls(map, { layerId, toggleId, opacityId, opacityValueId }) {
    const toggle = document.getElementById(toggleId);
    const slider = document.getElementById(opacityId);
    const readout = document.getElementById(opacityValueId);

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

    if (slider && readout) {
        readout.textContent = parseFloat(slider.value).toFixed(2);
        slider.addEventListener('input', () => {
            const value = parseFloat(slider.value);
            readout.textContent = value.toFixed(2);
            if (map.getLayer(layerId)) {
                map.setPaintProperty(layerId, 'raster-opacity', value);
            }
        });
    }
}
