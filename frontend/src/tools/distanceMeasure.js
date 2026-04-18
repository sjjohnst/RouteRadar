// Distance measurement tool: toggle the button, then left-click to add
// points to a path. Shows a polyline and running distance in the toolkit.

// Simple haversine distance between two lon/lat points in meters
function haversineDistance([lon1, lat1], [lon2, lat2]) {
    const toRad = (d) => (d * Math.PI) / 180;
    const R = 6371000; // Earth radius in meters

    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);
    const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

export function initDistanceMeasureTool(map) {
    const measureButton = document.getElementById('tool-measure');
    const output = document.getElementById('tool-output');

    if (!measureButton || !output) {
        return;
    }

    const sourceId = 'measure-line-source';
    const lineLayerId = 'measure-line-layer';
    const labelLayerId = 'measure-label-layer';

    let active = false;
    let measuring = false;
    let start = null;
    let current = null;
    let completed = false;
    let onDeactivated = null;

    const updateSourceData = () => {
        const source = map.getSource(sourceId);
        const features = [];

        if (start && current) {
            features.push({
                type: 'Feature',
                geometry: {
                    type: 'LineString',
                    coordinates: [start, current]
                },
                properties: {}
            });

            // midpoint for label
            const mid = [(start[0] + current[0]) / 2, (start[1] + current[1]) / 2];
            const dist = haversineDistance(start, current);
            features.push({
                type: 'Feature',
                geometry: {
                    type: 'Point',
                    coordinates: mid
                },
                properties: {
                    distance: `${dist.toFixed(0)} m`
                }
            });
        }

        const geojson = {
            type: 'FeatureCollection',
            features
        };

        if (source) {
            source.setData(geojson);
        }
    };

    const ensureSourceAndLayer = () => {
        if (!map.getSource(sourceId)) {
            map.addSource(sourceId, {
                type: 'geojson',
                data: {
                    type: 'FeatureCollection',
                    features: []
                }
            });
        }

        if (!map.getLayer(lineLayerId)) {
            map.addLayer({
                id: lineLayerId,
                type: 'line',
                source: sourceId,
                paint: {
                    'line-color': '#f97316',
                    'line-width': 3,
                    'line-dasharray': [2, 2]
                },
                filter: ['==', ['geometry-type'], 'LineString']
            });
        }

        if (!map.getLayer(labelLayerId)) {
            map.addLayer({
                id: labelLayerId,
                type: 'symbol',
                source: sourceId,
                layout: {
                    'text-field': ['get', 'distance'],
                    'text-size': 14,
                    'text-offset': [0, -0.6],
                    'text-anchor': 'top'
                },
                paint: {
                    'text-color': '#111',
                    'text-halo-color': '#fff',
                    'text-halo-width': 2
                },
                filter: ['==', ['geometry-type'], 'Point']
            });
        }
    };

    const mousemoveHandler = (event) => {
        if (!measuring) return;
        current = [event.lngLat.lng, event.lngLat.lat];
        updateSourceData();
        const dist = haversineDistance(start, current);
        output.textContent = `Distance: ${dist.toFixed(0)} m`;
    };

    const mouseupHandler = (event) => {
        if (!measuring) return;
        current = [event.lngLat.lng, event.lngLat.lat];
        measuring = false;
        completed = true;
        updateSourceData();
        const dist = haversineDistance(start, current);
        output.textContent = `Distance: ${dist.toFixed(0)} m`;

        map.getCanvas().style.cursor = '';
        try { map.dragPan.enable(); } catch (e) {}

        map.off('mousemove', mousemoveHandler);
        map.off('mouseup', mouseupHandler);

        // Automatically turn the tool off after finishing, but leave the measurement visible
        deactivate();
    };

    const mousedownHandler = (event) => {
        // start measuring
        start = [event.lngLat.lng, event.lngLat.lat];
        current = start.slice();
        measuring = true;
        completed = false;
        if (map.isStyleLoaded()) {
            ensureSourceAndLayer();
        } else {
            map.once('load', ensureSourceAndLayer);
        }

        updateSourceData();
        output.textContent = 'Drag to set end point...';
        map.getCanvas().style.cursor = 'crosshair';
        try { map.dragPan.disable(); } catch (e) {}

        map.on('mousemove', mousemoveHandler);
        map.on('mouseup', mouseupHandler);
    };

    const activate = (callbacks = {}) => {
        onDeactivated = callbacks.onDeactivated ?? null;
        if (active) return;
        active = true;
        measureButton.setAttribute('aria-pressed', 'true');

        if (map.isStyleLoaded()) {
            ensureSourceAndLayer();
        } else {
            map.once('load', ensureSourceAndLayer);
        }

        output.textContent = 'Hold mouse and drag to measure distance.';
        // Show crosshair cursor while the tool is active
        try { map.getCanvas().style.cursor = 'crosshair'; } catch (e) {}
        map.on('mousedown', mousedownHandler);
    };

    const deactivate = () => {
        if (!active) return;
        active = false;
        measureButton.setAttribute('aria-pressed', 'false');

        map.off('mousedown', mousedownHandler);
        map.off('mousemove', mousemoveHandler);
        map.off('mouseup', mouseupHandler);

        map.getCanvas().style.cursor = '';
        try { map.dragPan.enable(); } catch (e) {}

        // If the measurement hasn't been completed, clear drawings; otherwise leave them visible.
        if (!completed) {
            const source = map.getSource(sourceId);
            if (source) {
                source.setData({ type: 'FeatureCollection', features: [] });
            }
            output.textContent = '';
        }

        onDeactivated?.();
    };

    return { activate, deactivate, button: measureButton };
}
