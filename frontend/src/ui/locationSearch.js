// src/ui/locationSearch.js
// Simple location search using Nominatim (OpenStreetMap)

export function setupLocationSearch(map) {
    const input = document.getElementById('location-search-input');
    const btn = document.getElementById('location-search-btn');
    if (!input || !btn) return;

    btn.addEventListener('click', async () => {
        const query = input.value.trim();
        if (!query) return;
        // Nominatim API
        const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}`;
        try {
            const res = await fetch(url);
            const data = await res.json();
            if (data && data.length > 0) {
                const { lat, lon, display_name } = data[0];
                const bounds = map.getMaxBounds();
                if (bounds && bounds.contains([lon, lat])) {
                    map.setCenter([lon, lat]);
                    map.setZoom(14);
                    // Optionally show result
                    input.value = display_name; 
                } else {
                    input.value = 'Location out of bounds';
                }
            } else {
                input.value = 'Location not found';
            }
        } catch (err) {
            input.value = 'Error searching';
        }
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') btn.click();
    });
}
