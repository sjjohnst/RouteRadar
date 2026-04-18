// src/ui/initControls.js
// Initialises all sidebar control elements to their default values.
// Extracted from index.html so the Cloudflare Vite plugin can resolve
// the import correctly (it cannot process inline <script type="module"> tags).

import { layerDefaults } from '../config/layerDefaults.js';

// DTM
// document.getElementById('hrdem-wms-dtm-colormap').value = layerDefaults.dtm.colormap;
// document.getElementById('hrdem-wms-dtm-rescale').value = layerDefaults.dtm.rescale;

// Slope

// Hillshade

// Quebec Public Land
// Quebec Public Land
document.getElementById('toggle-quebec-public-land').checked = layerDefaults.quebecPublicLand.visible;
document.getElementById('quebec-public-land-opacity').value = layerDefaults.quebecPublicLand.opacity;
document.getElementById('quebec-public-land-opacity-value').textContent = layerDefaults.quebecPublicLand.opacity.toFixed(2);

// Relief mosaic
document.getElementById('toggle-relief').checked = layerDefaults.relief.visible;
document.getElementById('relief-opacity').value = layerDefaults.relief.opacity;
document.getElementById('relief-opacity-value').textContent = layerDefaults.relief.opacity.toFixed(2);
document.getElementById('relief-vmin').value = layerDefaults.relief.vminMetres;
document.getElementById('relief-vmax').value = layerDefaults.relief.vmaxMetres;
