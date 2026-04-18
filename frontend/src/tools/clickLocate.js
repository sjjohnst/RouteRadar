import maplibregl from 'maplibre-gl';

export function initClickLocateTool(map) {
    const markerButton = document.getElementById('tool-marker');
    if (!markerButton) return null;

    let active = false;
    let onDeactivated = null;
    const markers = [];

    const removeMarker = (marker) => {
        try {
            marker.remove();
        } catch (e) {}
        const idx = markers.indexOf(marker);
        if (idx !== -1) markers.splice(idx, 1);
    };

    const handleClick = (event) => {
        const { lng, lat } = event.lngLat;
        const lngStr = lng.toFixed(5);
        const latStr = lat.toFixed(5);

        // Create popup content with remove 'x' in the top-left and coords only
        const popupContent = document.createElement('div');
        popupContent.style.position = 'relative';
        popupContent.style.fontFamily = 'inherit';
        popupContent.style.fontSize = '13px';

        const removeBtn = document.createElement('button');
        removeBtn.textContent = '✕';
        removeBtn.setAttribute('aria-label', 'Remove marker');
        removeBtn.style.position = 'absolute';
        removeBtn.style.top = '2px';
        removeBtn.style.right = '4px';
        removeBtn.style.zIndex = '10';
        removeBtn.style.border = 'none';
        removeBtn.style.background = 'transparent';
        removeBtn.style.color = '#000';
        removeBtn.style.cursor = 'pointer';
        removeBtn.style.fontSize = '12px';
        removeBtn.style.lineHeight = '1';
        removeBtn.style.padding = '0';

        const coordsDiv = document.createElement('div');
        // Reserve space on the right so the remove button doesn't overlap the coords
        coordsDiv.style.padding = '6px 28px 6px 8px';
        coordsDiv.style.fontFamily = 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace';
        coordsDiv.style.fontSize = '13px';
        coordsDiv.style.lineHeight = '1.2';
        // Align labels and use monospaced numbers for even columns
        coordsDiv.innerHTML = `
            <div style="display:flex;gap:8px;align-items:center"><div style="min-width:40px;font-weight:600">Lng:</div><div style="font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, monospace">${lngStr}</div></div>
            <div style="display:flex;gap:8px;align-items:center"><div style="min-width:40px;font-weight:600">Lat:</div><div style="font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, monospace">${latStr}</div></div>
        `;

        popupContent.appendChild(removeBtn);
        popupContent.appendChild(coordsDiv);

        const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false }).setDOMContent(popupContent);

        const marker = new maplibregl.Marker().setLngLat([lng, lat]).setPopup(popup).addTo(map);
        markers.push(marker);

        // Do NOT open the popup immediately. Instead open it only when the user clicks the marker.
        // Add a click handler on the marker element and stop propagation so clicking the marker
        // doesn't create a new marker on the map behind it.
        const el = marker.getElement();
        let popupOpen = false;
        if (el) {
            el.style.cursor = 'pointer';
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                if (popupOpen) {
                    try { popup.remove(); } catch (err) {}
                    popupOpen = false;
                } else {
                    popup.addTo(map).setLngLat([lng, lat]);
                    popupOpen = true;
                }
            });
        }

        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            try { popup.remove(); } catch (err) {}
            popupOpen = false;
            removeMarker(marker);
        });
    };

    const activate = (callbacks = {}) => {
        onDeactivated = callbacks.onDeactivated ?? null;
        if (active) return;
        active = true;
        markerButton.setAttribute('aria-pressed', 'true');
        map.getCanvas().style.cursor = 'crosshair';
        map.on('click', handleClick);
    };

    const deactivate = () => {
        if (!active) return;
        active = false;
        markerButton.setAttribute('aria-pressed', 'false');
        map.getCanvas().style.cursor = '';
        map.off('click', handleClick);
        onDeactivated?.();
    };

    return { activate, deactivate, button: markerButton };
}
