import {
    HRDEM_WMS_DTM_LAYER_ID,
    HRDEM_WMS_SLOPE_LAYER_ID,
    HRDEM_WMS_HILLSHADE_LAYER_ID,
    buildHRDEMWmsUrl
} from '../map.js';

export function setupHrdemWmsControls(map) {

    // Helper to update DTM WMS source with rescale
    function updateDtmSource(rescale) {
        // Parse rescale string (e.g., "0,800")
        let min = 0, max = 800;
        if (rescale && rescale.includes(',')) {
            const parts = rescale.split(',');
            min = parseFloat(parts[0]);
            max = parseFloat(parts[1]);
        }
        // Build WMS URL with RGB rescale params
        let url = buildHRDEMWmsUrl('dtm');
        url += `&rescaleNewMinRed=${min}&rescaleNewMaxRed=${max}`;
        // url += `&rescaleNewMinGreen=${min}&rescaleNewMaxGreen=${max}`;
        // url += `&rescaleNewMinBlue=${min}&rescaleNewMaxBlue=${max}`;

        // Update the map source
        if (map.getSource('hrdem-wms-dtm')) {
            map.getSource('hrdem-wms-dtm').tiles = [url];
            // Remove and re-add layer to force refresh
            if (map.getLayer(HRDEM_WMS_DTM_LAYER_ID)) {
                map.removeLayer(HRDEM_WMS_DTM_LAYER_ID);
            }
            map.addLayer({
                id: HRDEM_WMS_DTM_LAYER_ID,
                type: 'raster',
                source: 'hrdem-wms-dtm',
                paint: { 'raster-opacity': parseFloat(dtmOpacitySlider.value) || 0.8 }
            });
        }
    }

    // DTM controls
    const dtmToggle = document.getElementById('toggle-hrdem-wms-dtm');
    const dtmOpacitySlider = document.getElementById('hrdem-wms-dtm-opacity');
    const dtmOpacityValue = document.getElementById('hrdem-wms-dtm-opacity-value');
    const dtmColormap = document.getElementById('hrdem-wms-dtm-colormap');
    const dtmRescale = document.getElementById('hrdem-wms-dtm-rescale');
    const dtmApplyBtn = document.getElementById('apply-hrdem-wms-dtm-params');

    if (dtmToggle) {
        dtmToggle.addEventListener('change', () => {
            if (map.getLayer(HRDEM_WMS_DTM_LAYER_ID)) {
                map.setLayoutProperty(
                    HRDEM_WMS_DTM_LAYER_ID,
                    'visibility',
                    dtmToggle.checked ? 'visible' : 'none'
                );
            }
        });
    }
    if (dtmOpacitySlider && dtmOpacityValue) {
        dtmOpacitySlider.addEventListener('input', () => {
            const value = parseFloat(dtmOpacitySlider.value);
            dtmOpacityValue.textContent = value.toFixed(2);
            if (map.getLayer(HRDEM_WMS_DTM_LAYER_ID)) {
                map.setPaintProperty(HRDEM_WMS_DTM_LAYER_ID, 'raster-opacity', value);
            }
        });
    }
    // DTM Apply: update WMS source with rescale and colormap
    if (dtmApplyBtn) {
        dtmApplyBtn.addEventListener('click', () => {
            const colormap = dtmColormap.value;
            const rescale = dtmRescale.value;
            updateDtmSource(colormap, rescale);
        });
    }
    
    // Slope controls
    const slopeToggle = document.getElementById('toggle-hrdem-wms-slope');
    const slopeOpacitySlider = document.getElementById('hrdem-wms-slope-opacity');
    const slopeOpacityValue = document.getElementById('hrdem-wms-slope-opacity-value');
    if (slopeToggle) {
        slopeToggle.addEventListener('change', () => {
            if (map.getLayer(HRDEM_WMS_SLOPE_LAYER_ID)) {
                map.setLayoutProperty(
                    HRDEM_WMS_SLOPE_LAYER_ID,
                    'visibility',
                    slopeToggle.checked ? 'visible' : 'none'
                );
            }
        });
    }
    if (slopeOpacitySlider && slopeOpacityValue) {
        slopeOpacitySlider.addEventListener('input', () => {
            const value = parseFloat(slopeOpacitySlider.value);
            slopeOpacityValue.textContent = value.toFixed(2);
            if (map.getLayer(HRDEM_WMS_SLOPE_LAYER_ID)) {
                map.setPaintProperty(HRDEM_WMS_SLOPE_LAYER_ID, 'raster-opacity', value);
            }
        });
    }

    // Hillshade controls
    const hillshadeToggle = document.getElementById('toggle-hrdem-wms-hillshade');
    const hillshadeOpacitySlider = document.getElementById('hrdem-wms-hillshade-opacity');
    const hillshadeOpacityValue = document.getElementById('hrdem-wms-hillshade-opacity-value');
    if (hillshadeToggle) {
        hillshadeToggle.addEventListener('change', () => {
            if (map.getLayer(HRDEM_WMS_HILLSHADE_LAYER_ID)) {
                map.setLayoutProperty(
                    HRDEM_WMS_HILLSHADE_LAYER_ID,
                    'visibility',
                    hillshadeToggle.checked ? 'visible' : 'none'
                );
            }
        });
    }
    if (hillshadeOpacitySlider && hillshadeOpacityValue) {
        hillshadeOpacitySlider.addEventListener('input', () => {
            const value = parseFloat(hillshadeOpacitySlider.value);
            hillshadeOpacityValue.textContent = value.toFixed(2);
            if (map.getLayer(HRDEM_WMS_HILLSHADE_LAYER_ID)) {
                map.setPaintProperty(HRDEM_WMS_HILLSHADE_LAYER_ID, 'raster-opacity', value);
            }
        });
    }
}
