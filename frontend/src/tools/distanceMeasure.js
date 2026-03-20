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
    const layerId = 'measure-line-layer';

    let active = false;
    let points = [];

    const updateLine = () => {
        const source = map.getSource(sourceId);
        const geojson = {
            type: 'FeatureCollection',
            features: []
        };

        if (points.length > 1) {
            geojson.features.push({
                type: 'Feature',
                geometry: {
                    type: 'LineString',
                    coordinates: points
                },
                properties: {}
            });
        }

        if (source) {
            source.setData(geojson);
        }
    };

    const updateDistanceOutput = () => {
        if (points.length < 2) {
            output.textContent = 'Click to add points for distance measurement.';
            return;
        }

        let total = 0;
        for (let i = 1; i < points.length; i++) {
            total += haversineDistance(points[i - 1], points[i]);
        }

        const km = total / 1000;
        output.textContent = `Distance: ${total.toFixed(0)} m`;
    };

    const clickHandler = (event) => {
        const { lng, lat } = event.lngLat;
        points.push([lng, lat]);
        updateLine();
        updateDistanceOutput();
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

        if (!map.getLayer(layerId)) {
            map.addLayer({
                id: layerId,
                type: 'line',
                source: sourceId,
                paint: {
                    'line-color': '#f97316',
                    'line-width': 3,
                    'line-dasharray': [2, 2]
                }
            });
        }
    };

    const activate = () => {
        if (active) return;
        active = true;
        measureButton.classList.add('active-tool');
        points = [];

        if (map.isStyleLoaded()) {
            ensureSourceAndLayer();
        } else {
            map.once('load', ensureSourceAndLayer);
        }

        output.textContent = 'Click on the map to add points.';
        map.on('click', clickHandler);
    };

    const deactivate = () => {
        if (!active) return;
        active = false;
        measureButton.classList.remove('active-tool');
        map.off('click', clickHandler);

        points = [];
        const source = map.getSource(sourceId);
        if (source) {
            source.setData({ type: 'FeatureCollection', features: [] });
        }
        output.textContent = '';
    };

    measureButton.addEventListener('click', () => {
        if (active) {
            deactivate();
        } else {
            activate();
        }
    });
}
