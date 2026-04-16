import './style.css';
import maplibregl from 'maplibre-gl';
import { MapLibreSearchControl } from '@stadiamaps/maplibre-search-box';
import '@stadiamaps/maplibre-search-box/dist/maplibre-search-box.css';
import { initMap, applyAoiFromGeojson, registerTilerProtocol } from './src/map.js';
import { setupReliefControls } from './src/ui/mosaicControls.js';
import { initClickLocateTool } from './src/tools/clickLocate.js';
import { initDistanceMeasureTool } from './src/tools/distanceMeasure.js';
import { setupQuebecPublicLandControls } from './src/ui/quebecPublicLandControls.js';
import { setupInfoTool } from './src/ui/infoTool.js';

// Register custom "tiler://" protocol for per-tile 503 retry with back-off.
// Must be called before initMap() so the source URL is already handled.
registerTilerProtocol(maplibregl);

// Bootstrap map
const map = await initMap();

// Add MapLibreSearchControl (autocomplete search box)
let aoiBounds = null;
// We'll log the bounds after map is ready

// Helper to update AOI bounds from map
function updateAoiBoundsFromMap() {
	const b = map.getMaxBounds();
	if (b) {
		aoiBounds = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
		console.log('AOI bounds:', aoiBounds);
	} else {
		console.log('No AOI bounds set');
	}
}

// After AOI is applied, update bounds
applyAoiFromGeojson(map).then(() => {
	updateAoiBoundsFromMap();
}).catch((err) => {
	console.error('Failed to apply AOI from GeoJSON', err);
});

const searchControl = new MapLibreSearchControl({
	useMapFocusPoint: true,
	onResultSelected: feature => {
		console.log('Search result selected:', feature);
		// Only allow flyTo for valid, in-bounds results
		if (!feature.geometry || !feature.geometry.coordinates) {
			console.log('No geometry/coordinates in result');
			return false;
		}
		const [lng, lat] = feature.geometry.coordinates;
		console.log('Result coordinates:', lng, lat);
		let outOfBounds = false;
		if (aoiBounds) {
			const [minLng, minLat, maxLng, maxLat] = aoiBounds;
			console.log('Checking bounds:', minLng, minLat, maxLng, maxLat);
			if (lng < minLng || lng > maxLng || lat < minLat || lat > maxLat) {
				outOfBounds = true;
				console.log('Result is OUT OF BOUNDS');
			} else {
				console.log('Result is within bounds');
			}
		} else {
			console.log('No AOI bounds to check against');
		}
		if (outOfBounds) {
			// Show popup but do NOT allow any zoom
			new maplibregl.Popup()
				.setLngLat([lng, lat])
				.setHTML('<b>Out of bounds</b>')
				.addTo(map);
			return false;
		}
		// Only here if valid and in bounds
		map.flyTo({ center: [lng, lat], zoom: 13 });
		return true;
	}
});
map.addControl(searchControl, 'top-right');

// Wire UI modules
await setupReliefControls(map);
setupQuebecPublicLandControls(map);
setupInfoTool(map);
initClickLocateTool(map);
initDistanceMeasureTool(map);

// Apply AOI constraints from GeoJSON
applyAoiFromGeojson(map).catch((err) => {
	console.error('Failed to apply AOI from GeoJSON', err);
});
