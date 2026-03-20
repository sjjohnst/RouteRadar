import maplibregl from 'maplibre-gl';

// Drop marker tool: toggle the button, then left-click on the map
// to show coordinates in the toolkit and in a popup.
export function initClickLocateTool(map) {
    const output = document.getElementById('tool-output');
    const markerButton = document.getElementById('tool-marker');

    if (!output || !markerButton) {
        return;
    }

    let active = false;
    let popup = null;

    const handleClick = (event) => {
        const { lng, lat } = event.lngLat;
        const lngStr = lng.toFixed(5);
        const latStr = lat.toFixed(5);

        output.textContent = `Marker at ${lngStr}, ${latStr}`;

        const html = `<div><strong>Marker</strong><br>Lng: ${lngStr}<br>Lat: ${latStr}</div>`;

        if (!popup) {
            popup = new maplibregl.Popup({ closeOnClick: false })
                .setLngLat([lng, lat])
                .setHTML(html)
                .addTo(map);
        } else {
            popup.setLngLat([lng, lat]).setHTML(html);
        }
    };

    const activate = () => {
        if (active) return;
        active = true;
        markerButton.classList.add('active-tool');
        output.textContent = 'Click on the map to drop a marker.';
        map.on('click', handleClick);
    };

    const deactivate = () => {
        if (!active) return;
        active = false;
        markerButton.classList.remove('active-tool');
        output.textContent = '';
        map.off('click', handleClick);
    };

    markerButton.addEventListener('click', () => {
        if (active) {
            deactivate();
        } else {
            activate();
        }
    });
}
