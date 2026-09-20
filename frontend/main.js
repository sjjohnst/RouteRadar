import './style.css';
import maplibregl from 'maplibre-gl';
import { MapLibreSearchControl } from '@stadiamaps/maplibre-search-box';
import '@stadiamaps/maplibre-search-box/dist/maplibre-search-box.css';
import { initMap } from './src/map.js';
import { registerTilerProtocol } from './src/tilerProtocol.js';
import { containsPoint } from './src/aoi.js';
import { setupReliefControls } from './src/ui/mosaicControls.js';
import { initClickLocateTool } from './src/tools/clickLocate.js';
import { initDistanceMeasureTool } from './src/tools/distanceMeasure.js';
import { setupQuebecPublicLandControls } from './src/ui/quebecPublicLandControls.js';
import { setupInfoTool } from './src/tools/infoTool.js';
import { initHelpGuide } from './src/ui/helpGuide.js';

// Register custom "tiler://" protocol for per-tile 503 retry with back-off.
// Must be called before initMap() so the source URL is already handled.
registerTilerProtocol(maplibregl);

// Bootstrap map
const map = await initMap();

const searchControl = new MapLibreSearchControl({
	useMapFocusPoint: true,
	onResultSelected: feature => {
		// Only allow flyTo for valid, in-bounds results
		if (!feature.geometry || !feature.geometry.coordinates) {
			return false;
		}
		const [lng, lat] = feature.geometry.coordinates;
		if (!containsPoint([lng, lat])) {
			// Show popup but do NOT allow any zoom
			new maplibregl.Popup()
				.setLngLat([lng, lat])
				.setHTML('<b>Out of bounds</b>')
				.addTo(map);
			return false;
		}
		map.flyTo({ center: [lng, lat], zoom: 13 });
		return true;
	}
});
map.addControl(searchControl, 'top-right');

// Wire UI modules
await setupReliefControls(map);
setupQuebecPublicLandControls(map);
const infoTool = setupInfoTool(map);
const markerTool = initClickLocateTool(map);
const measureTool = initDistanceMeasureTool(map);
initHelpGuide();

// GIS toolbar zoom buttons
document.getElementById('gis-zoom-in')?.addEventListener('click', () => map.zoomIn());
document.getElementById('gis-zoom-out')?.addEventListener('click', () => map.zoomOut());

// Tool coordinator: mutual exclusion, one tool active at a time
let currentTool = null;
const tools = [infoTool, markerTool, measureTool].filter(Boolean);

function setActiveTool(tool) {
    if (currentTool && currentTool !== tool) {
        currentTool.deactivate();
    }
    currentTool = tool;
    if (tool) tool.activate({ onDeactivated: () => { currentTool = null; } });
}

tools.forEach((tool) => {
    tool.button.addEventListener('click', () => {
        if (currentTool === tool) {
            // Toggle off
            tool.deactivate();
            currentTool = null;
        } else {
            setActiveTool(tool);
        }
    });
});
