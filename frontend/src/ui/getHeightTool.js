// src/ui/getHeightTool.js
// Tool to get height at a point by querying the backend mosaicjson/point endpoint.
// The backend holds the mosaic in memory (MemoryBackend), so no `url` param is needed.

export function setupGetHeightTool(map) {
    const btn = document.getElementById('tool-get-height');
    const toolOutput = document.getElementById('tool-output');
    let active = false;
    let clickHandler = null;

    if (!btn || !toolOutput) return;

    btn.addEventListener('click', () => {
        active = !active;
        btn.classList.toggle('active', active);
        toolOutput.textContent = active ? 'Click on the map to get height...' : '';
        if (active) {
            clickHandler = async (e) => {
                const lngLat = e.lngLat;
                toolOutput.textContent = 'Querying height...';
                try {
                    const url = `/mosaicjson/point/${lngLat.lng},${lngLat.lat}`;
                    const res = await fetch(url);
                    const data = await res.json();
                    // mosaicjson/point returns { values: [[band, value, ...], ...] }
                    const val = data?.values?.[0]?.[0];
                    if (val !== undefined && val !== null) {
                        toolOutput.textContent = `Height at (${lngLat.lat.toFixed(5)}, ${lngLat.lng.toFixed(5)}): ${val.toFixed(2)} m`;
                    } else {
                        toolOutput.textContent = 'No height data at this location.';
                    }
                } catch (err) {
                    toolOutput.textContent = 'Error querying height.';
                    console.error('Error querying height:', err);
                }
            };
            map.on('click', clickHandler);
        } else {
            if (clickHandler) map.off('click', clickHandler);
            clickHandler = null;
        }
    });
}
