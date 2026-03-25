const WMS_BASE = '/patp-wms';
const WMS_LAYER = 'Affectations surfaciques';
const GFI_SIZE = 256;
const EARTH_RADIUS = 6378137;
const MAX_MERCATOR_LAT = 85.05112878;

const STATUS_IDLE = 'Activate the tool and click on the map.';
const STATUS_READY = 'Click on the map to retrieve information.';
const STATUS_QUERYING = 'Querying map services…';
const STATUS_ERROR = 'Unable to fetch some map data.';

const NAME_KEYS = ['NOMZONE', 'NOM_ZONE', 'NOM_AFFECT', 'NOM'];
const ID_KEYS = ['ID', 'ID_ZONE', 'ZONE_ID', 'ID_AFFECT'];
const DATE_KEYS = ['DATE', 'DATE_MAJ', 'DATE_MAJZONE', 'DATEAFFECT'];
const SUBZONE_KEYS = ['NOMSOUSZONE', 'NOM_SOUS_ZONE', 'SOUSZONE'];

function clampLat(lat) {
    return Math.max(Math.min(lat, MAX_MERCATOR_LAT), -MAX_MERCATOR_LAT);
}

function lngLatToWebMercator(lng, lat) {
    const lambda = (lng * Math.PI) / 180;
    const phi = (clampLat(lat) * Math.PI) / 180;
    const x = EARTH_RADIUS * lambda;
    const y = EARTH_RADIUS * Math.log(Math.tan(Math.PI / 4 + phi / 2));
    return { x, y };
}

function buildGetFeatureInfoUrl(map, lngLat) {
    const canvas = map.getCanvas();
    const bounds = map.getBounds();
    const sw = lngLatToWebMercator(bounds.getSouthWest().lng, bounds.getSouthWest().lat);
    const ne = lngLatToWebMercator(bounds.getNorthEast().lng, bounds.getNorthEast().lat);

    const minX = Math.min(sw.x, ne.x);
    const maxX = Math.max(sw.x, ne.x);
    const minY = Math.min(sw.y, ne.y);
    const maxY = Math.max(sw.y, ne.y);

    const point = map.project(lngLat);
    const I = Math.round((point.x / canvas.width) * GFI_SIZE);
    const J = Math.round((point.y / canvas.height) * GFI_SIZE);

    const params = new URLSearchParams({
        SERVICE: 'WMS',
        VERSION: '1.3.0',
        REQUEST: 'GetFeatureInfo',
        LAYERS: WMS_LAYER,
        QUERY_LAYERS: WMS_LAYER,
        INFO_FORMAT: 'application/geojson',
        FEATURE_COUNT: 5,
        CRS: 'EPSG:3857',
        WIDTH: GFI_SIZE,
        HEIGHT: GFI_SIZE,
        BBOX: `${minX},${minY},${maxX},${maxY}`,
        I,
        J,
    });

    return `${WMS_BASE}?${params.toString()}`;
}

function pickProp(props, keys) {
    for (const key of keys) {
        if (props[key] !== undefined && props[key] !== null && props[key] !== '') {
            return props[key];
        }
        const alt = key.toLowerCase();
        if (props[alt] !== undefined && props[alt] !== null && props[alt] !== '') {
            return props[alt];
        }
    }
    return null;
}

function normalisePublicLand(feature) {
    if (!feature) return null;
    const props = feature.properties || {};
    return {
        name: pickProp(props, NAME_KEYS) ?? 'NULL',
        id: pickProp(props, ID_KEYS) ?? 'N/A',
        date: pickProp(props, DATE_KEYS) ?? 'N/A',
        subzone: pickProp(props, SUBZONE_KEYS) ?? 'N/A',
    };
}

function formatCoords(lng, lat) {
    return `(${lat.toFixed(5)}, ${lng.toFixed(5)})`;
}

async function fetchReliefValue(lng, lat, signal) {
    const res = await fetch(`/relief/point?lng=${lng}&lat=${lat}`, { signal });
    if (!res.ok) {
        throw new Error(`Relief point request failed: ${res.status}`);
    }
    const data = await res.json();
    if (typeof data.elevation_m === 'number') {
        return data.elevation_m;
    }
    return null;
}

async function fetchPublicLandFeature(map, lngLat, signal) {
    const url = buildGetFeatureInfoUrl(map, lngLat);
    const res = await fetch(url, { signal });
    if (!res.ok) {
        throw new Error(`Public land GetFeatureInfo failed: ${res.status}`);
    }
    const geojson = await res.json();
    const features = geojson.features ?? [];
    return features[0] ?? null;
}

function isAbortError(err) {
    return err?.name === 'AbortError';
}

function toggleDetails(detailsBtn, detailsPanel, expanded) {
    if (!detailsBtn || !detailsPanel) return;
    detailsBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    const chevron = detailsBtn.querySelector('.chevron');
    if (chevron) {
        chevron.textContent = expanded ? '▾' : '▸';
    }
    detailsPanel.classList.toggle('hidden', !expanded);
}

export function setupInfoTool(map) {
    const button = document.getElementById('tool-info');
    const coordsEl = document.getElementById('info-tool-coords');
    const reliefEl = document.getElementById('info-tool-relief');
    const publicNameEl = document.getElementById('info-tool-public-name');
    const publicIdEl = document.getElementById('info-tool-public-id');
    const publicDateEl = document.getElementById('info-tool-public-date');
    const publicSubzoneEl = document.getElementById('info-tool-public-subzone');
    const statusEl = document.getElementById('info-tool-status');
    const detailsBtn = document.getElementById('info-tool-public-expand');
    const detailsPanel = document.getElementById('info-tool-public-details');

    if (!button || !coordsEl || !reliefEl || !publicNameEl || !publicIdEl || !publicDateEl || !publicSubzoneEl || !statusEl || !detailsBtn || !detailsPanel) {
        console.warn('Info tool markup missing; skipping setup.');
        return;
    }

    const setStatus = (msg) => {
        statusEl.textContent = msg;
    };

    const resetPublicInfo = () => {
        publicNameEl.textContent = 'NULL';
        publicIdEl.textContent = 'N/A';
        publicDateEl.textContent = 'N/A';
        publicSubzoneEl.textContent = 'N/A';
        detailsBtn.disabled = true;
        toggleDetails(detailsBtn, detailsPanel, false);
    };

    const setPublicInfo = (info) => {
        if (!info) {
            resetPublicInfo();
            return;
        }
        publicNameEl.textContent = info.name;
        publicIdEl.textContent = info.id;
        publicDateEl.textContent = info.date;
        publicSubzoneEl.textContent = info.subzone;
        detailsBtn.disabled = info.name === 'NULL' && info.id === 'N/A' && info.date === 'N/A' && info.subzone === 'N/A';
        if (detailsBtn.disabled) {
            toggleDetails(detailsBtn, detailsPanel, false);
        }
    };

    const resetUi = () => {
        coordsEl.textContent = '—';
        reliefEl.textContent = 'N/A';
        resetPublicInfo();
        setStatus(STATUS_IDLE);
    };

    resetUi();

    let active = false;
    let clickHandler = null;
    let activeController = null;

    const deactivate = () => {
        active = false;
        button.classList.remove('active-tool');
        button.setAttribute('aria-pressed', 'false');
        map.getCanvas().style.cursor = '';
        if (clickHandler) {
            map.off('click', clickHandler);
            clickHandler = null;
        }
        if (activeController) {
            activeController.abort();
            activeController = null;
        }
        setStatus(STATUS_IDLE);
    };

    const handleClick = async (e) => {
        if (activeController) {
            activeController.abort();
        }
        const controller = new AbortController();
        activeController = controller;

        const { lng, lat } = e.lngLat;
        coordsEl.textContent = formatCoords(lng, lat);
        reliefEl.textContent = 'Loading…';
        publicNameEl.textContent = 'Loading…';
        publicIdEl.textContent = '—';
        publicDateEl.textContent = '—';
        publicSubzoneEl.textContent = '—';
        detailsBtn.disabled = true;
        toggleDetails(detailsBtn, detailsPanel, false);
        setStatus(STATUS_QUERYING);

        const reliefPromise = fetchReliefValue(lng, lat, controller.signal);
        const publicPromise = fetchPublicLandFeature(map, e.lngLat, controller.signal);

        try {
            const [reliefResult, publicResult] = await Promise.allSettled([reliefPromise, publicPromise]);
            if (controller.signal.aborted) {
                return;
            }

            if (reliefResult.status === 'fulfilled') {
                const value = reliefResult.value;
                reliefEl.textContent = value === null ? 'N/A' : `${value.toFixed(2)} m`;
            } else if (!isAbortError(reliefResult.reason)) {
                reliefEl.textContent = 'N/A';
            }

            if (publicResult.status === 'fulfilled') {
                const info = normalisePublicLand(publicResult.value);
                setPublicInfo(info);
            } else if (!isAbortError(publicResult.reason)) {
                resetPublicInfo();
            }

            if (
                reliefResult.status === 'rejected' && !isAbortError(reliefResult.reason) ||
                publicResult.status === 'rejected' && !isAbortError(publicResult.reason)
            ) {
                setStatus(STATUS_ERROR);
            } else {
                setStatus('Data retrieved.');
            }
        } catch (err) {
            if (isAbortError(err)) {
                return;
            }
            console.error('Info tool error:', err);
            reliefEl.textContent = 'N/A';
            resetPublicInfo();
            setStatus(STATUS_ERROR);
        } finally {
            if (activeController === controller) {
                activeController = null;
            }
        }
    };

    button.addEventListener('click', () => {
        if (active) {
            deactivate();
            return;
        }
        active = true;
        button.classList.add('active-tool');
        button.setAttribute('aria-pressed', 'true');
        setStatus(STATUS_READY);
        map.getCanvas().style.cursor = 'crosshair';
        clickHandler = handleClick;
        map.on('click', clickHandler);
    });

    detailsBtn.addEventListener('click', () => {
        if (detailsBtn.disabled) return;
        const expanded = detailsBtn.getAttribute('aria-expanded') === 'true';
        toggleDetails(detailsBtn, detailsPanel, !expanded);
    });

    return {
        deactivate,
    };
}
