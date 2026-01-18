import './style.css'
import { initMap } from './src/map.js'

// Initialize the map when the page loads
const map = initMap();

// Example: Listen for a click to "drop a pin" (we'll save this to Supabase later!)
map.on('click', (e) => {
    console.log(`Pin dropped at: ${e.lngLat}`);
    new maplibregl.Marker()
        .setLngLat(e.lngLat)
        .addTo(map);
});