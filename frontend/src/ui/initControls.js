// src/ui/initControls.js
// Initialises all sidebar control elements to their default values.
// Extracted from index.html so the Cloudflare Vite plugin can resolve
// the import correctly (it cannot process inline <script type="module"> tags).

import { layerDefaults } from '../config/layerDefaults.js';

// DTM
document.getElementById('toggle-hrdem-wms-dtm').checked = layerDefaults.dtm.visible;
document.getElementById('hrdem-wms-dtm-opacity').value = layerDefaults.dtm.opacity;
document.getElementById('hrdem-wms-dtm-opacity-value').textContent = layerDefaults.dtm.opacity;
// document.getElementById('hrdem-wms-dtm-colormap').value = layerDefaults.dtm.colormap;
// document.getElementById('hrdem-wms-dtm-rescale').value = layerDefaults.dtm.rescale;

// Slope
document.getElementById('toggle-hrdem-wms-slope').checked = layerDefaults.slope.visible;
document.getElementById('hrdem-wms-slope-opacity').value = layerDefaults.slope.opacity;
document.getElementById('hrdem-wms-slope-opacity-value').textContent = layerDefaults.slope.opacity;

// Hillshade
document.getElementById('toggle-hrdem-wms-hillshade').checked = layerDefaults.hillshade.visible;
document.getElementById('hrdem-wms-hillshade-opacity').value = layerDefaults.hillshade.opacity;
document.getElementById('hrdem-wms-hillshade-opacity-value').textContent = layerDefaults.hillshade.opacity;

// Quebec Public Land
document.getElementById('toggle-quebec-public-land').checked = layerDefaults.quebecPublicLand.visible;
document.getElementById('quebec-public-land-opacity').value = layerDefaults.quebecPublicLand.opacity;
document.getElementById('quebec-public-land-opacity-value').textContent = layerDefaults.quebecPublicLand.opacity;

// Relief mosaic
document.getElementById('toggle-relief').checked = layerDefaults.relief.visible;
document.getElementById('relief-opacity').value = layerDefaults.relief.opacity;
document.getElementById('relief-opacity-value').textContent = layerDefaults.relief.opacity;
document.getElementById('relief-vmin').value = layerDefaults.relief.vminMetres;
document.getElementById('relief-vmax').value = layerDefaults.relief.vmaxMetres;
