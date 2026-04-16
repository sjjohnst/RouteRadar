import './style.css'
import maplibregl from 'maplibre-gl'
import { initMap, applyAoiFromGeojson, registerTilerProtocol } from './src/map.js'
import { setupReliefControls } from './src/ui/mosaicControls.js'
import { setupHrdemWmsControls } from './src/ui/hrdemWmsControls.js'
import { setupToolkitToggle } from './src/ui/toolkitToggle.js'
import { initClickLocateTool } from './src/tools/clickLocate.js'
import { initDistanceMeasureTool } from './src/tools/distanceMeasure.js'
import { setupLocationSearch } from './src/ui/locationSearch.js';
import { setupQuebecPublicLandControls } from './src/ui/quebecPublicLandControls.js';
import { setupInfoTool } from './src/ui/infoTool.js';

// Register custom "tiler://" protocol for per-tile 503 retry with back-off.
// Must be called before initMap() so the source URL is already handled.
registerTilerProtocol(maplibregl);

// Bootstrap map
const map = await initMap();

// Wire UI modules
await setupReliefControls(map);
setupHrdemWmsControls(map);
setupToolkitToggle();
setupLocationSearch(map);
setupQuebecPublicLandControls(map);
setupInfoTool(map);
initClickLocateTool(map);
initDistanceMeasureTool(map);

// Apply AOI constraints from GeoJSON
applyAoiFromGeojson(map).catch((err) => {
	console.error('Failed to apply AOI from GeoJSON', err);
});
