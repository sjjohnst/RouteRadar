import maplibregl from 'maplibre-gl';
import { BACKEND_URL } from '../config/api.js';

const WMS_BASE = '/patp-wms';
const WMS_LAYER = 'Affectations surfaciques';
const GFI_SIZE = 256;
const EARTH_RADIUS = 6378137;
const MAX_MERCATOR_LAT = 85.05112878;

const STATUS_IDLE = 'Activate the tool and click on the map.';
const STATUS_READY = 'Click on the map to retrieve information.';
const STATUS_QUERYING = 'Querying map services…';
const STATUS_ERROR = 'Unable to fetch some map data.';
const STATUS_SUCCESS = 'Placard updated on the map.';

const NAME_KEYS = ['NOMZONE'];
const ID_KEYS = ['Identifiant'];
const DATE_KEYS = ['Date'];
const USE_KEYS = ['Vocation'];
const FULL_NAME_KEYS = ['NOMSOUSZONE'];

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

function cleanValue(value) {
    if (value === null || value === undefined) return null;
    if (typeof value === 'string') {
        const trimmed = value.trim();
        if (!trimmed || trimmed.toLowerCase() === 'null') {
            return null;
        }
        return trimmed;
    }
    return value;
}

function pickProp(props, keys) {
    for (const key of keys) {
        const direct = cleanValue(props[key]);
        if (direct !== null && direct !== undefined) {
            return direct;
        }
        const altKey = key.toLowerCase();
        const alt = cleanValue(props[altKey]);
        if (alt !== null && alt !== undefined) {
            return alt;
        }
    }
    return null;
}

function normalisePublicLand(feature) {
    if (!feature) return null;
    const props = feature.properties || {};
    if (props && typeof props === 'object') {
        try {
            console.debug('Info tool public land keys:', Object.keys(props));
        } catch (err) {
            console.debug('Info tool public land keys: <unavailable>', err);
        }
    }
    return {
        name: pickProp(props, NAME_KEYS) ?? 'NULL',
        id: pickProp(props, ID_KEYS) ?? 'N/A',
        date: pickProp(props, DATE_KEYS) ?? 'N/A',
        use: pickProp(props, USE_KEYS) ?? 'N/A',
        fullName: pickProp(props, FULL_NAME_KEYS) ?? 'N/A',
    };
}

// Coordinates formatting and relief fetching were removed — the info popup now shows only
// public/private land information returned by the WMS GetFeatureInfo call.

async function fetchPublicLandFeature(map, lngLat, signal) {
    const url = buildGetFeatureInfoUrl(map, lngLat);
    const res = await fetch(url, { signal });
    if (!res.ok) {
        throw new Error(`Public land GetFeatureInfo failed: ${res.status}`);
    }
    const geojson = await res.json();
    console.log('Info tool GetFeatureInfo response:', geojson);
    const features = geojson.features ?? [];
    if (features[0]?.properties) {
        console.log('Info tool first feature properties:', features[0].properties);
    }
    return features[0] ?? null;
}

function isAbortError(err) {
    return err?.name === 'AbortError';
}

function buildPopupHtml({ publicInfo }) {
    const info = publicInfo ?? { name: 'NULL', id: 'N/A', date: 'N/A', use: 'N/A', fullName: 'N/A' };
    if (info.name === 'NULL') {
        return `<div class="info-popup"><div class="info-popup-row"><span class="info-popup-value">Private</span></div></div>`;
    }
    return `
        <div class="info-popup">
            <details class="info-popup-details">
                <summary>
                    <span class="info-popup-label">Public/Protected:</span>
                    <span class="info-popup-value">${info.name}</span>
                </summary>
                <div class="info-popup-detail">
                    <span class="info-popup-detail-label">Full Name</span>
                    <span class="info-popup-detail-value">${info.fullName}</span>
                </div>
                <div class="info-popup-detail">
                    <span class="info-popup-detail-label">Id</span>
                    <span class="info-popup-detail-value">${info.id}</span>
                </div>
                <div class="info-popup-detail">
                    <span class="info-popup-detail-label">Use</span>
                    <span class="info-popup-detail-value">${info.use}</span>
                </div>
                <div class="info-popup-detail">
                    <span class="info-popup-detail-label">Date</span>
                    <span class="info-popup-detail-value">${info.date}</span>
                </div>
            </details>
        </div>
    `;
}

export function setupInfoTool(map) {
    const button = document.getElementById('tool-info');
    const statusEl = document.getElementById('info-tool-status');

    if (!button || !statusEl) {
        console.warn('Info tool markup missing; skipping setup.');
        return;
    }

    const setStatus = (msg) => {
        statusEl.textContent = msg;
    };

    setStatus(STATUS_IDLE);

    let active = false;
    let clickHandler = null;
    let activeController = null;
    let popup = null;

    const showPopup = (lngLat, publicInfo) => {
        const html = buildPopupHtml({ publicInfo });
        if (popup) {
            popup.remove();
        }
        popup = new maplibregl.Popup({ maxWidth: '320px', closeOnClick: false })
            .setLngLat(lngLat)
            .setHTML(html)
            .addTo(map);
    };

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

        setStatus(STATUS_QUERYING);

        try {
            const publicResult = await fetchPublicLandFeature(map, e.lngLat, controller.signal);
            if (controller.signal.aborted) return;
            const publicInfo = normalisePublicLand(publicResult);
            showPopup(e.lngLat, publicInfo);
            setStatus(STATUS_SUCCESS);
        } catch (err) {
            if (isAbortError(err)) return;
            console.error('Info tool public land fetch failed:', err);
            showPopup(e.lngLat, null);
            setStatus(STATUS_ERROR);
        } finally {
            if (activeController === controller) {
                activeController = null;
            }
        }
    };

    let onDeactivatedCb = null;

    const activateInternal = () => {
        active = true;
        button.classList.add('active-tool');
        button.setAttribute('aria-pressed', 'true');
        setStatus(STATUS_READY);
        map.getCanvas().style.cursor = 'crosshair';
        clickHandler = async (e) => {
            deactivate();
            onDeactivatedCb?.();
            await handleClick(e);
        };
        map.on('click', clickHandler);
    };

    const activate = (callbacks = {}) => {
        onDeactivatedCb = callbacks.onDeactivated ?? null;
        if (!active) activateInternal();
    };

    return {
        activate,
        deactivate,
        button,
    };
}
