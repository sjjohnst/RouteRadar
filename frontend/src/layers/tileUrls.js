// Tile URL templates for the raster layers the map builds its style from.
import { BACKEND_URL, QUEBEC_PUBLIC_LAND_WMS_URL } from '../config/api.js';
import { layerDefaults } from '../config/layerDefaults.js';
import { toTilerUrl } from '../tilerProtocol.js';

/** Packing to assume when the backend can't tell us; matches the ingestion default. */
export const FALLBACK_PACKING = { scale_factor: 0.01, add_offset: 0.0 };

/**
 * A TiTiler relief tile template, with the display range converted from metres
 * to the raw DN the COGs are packed in.
 *
 * The colormap is fixed: ui/reliefColorbar.js paints the legend from a
 * hardcoded cividis palette, so a second ramp here would disagree with it.
 * Making it a choice again means teaching the colorbar to derive its stops
 * from the same name.
 *
 * @param {number} vminMetres
 * @param {number} vmaxMetres
 * @param {{scale_factor: number, add_offset: number}} packing
 * @returns {string} tile URL template with {z}/{x}/{y}
 */
export function reliefTileUrl(vminMetres, vmaxMetres, packing) {
    const toDN = (metres) => Math.round((metres - packing.add_offset) / packing.scale_factor);

    const params = new URLSearchParams({
        rescale: `${toDN(vminMetres)},${toDN(vmaxMetres)}`,
        colormap_name: layerDefaults.relief.colormap,
    });
    // Request .webp explicitly. Without this TiTiler auto-selects JPEG so relief
    // would be served lossily (RMSE ~6.9, single pixels off by up to 177/255).
    // Requires that the backend renders WebP losslessly.
    return toTilerUrl(
        `${BACKEND_URL}/mosaicjson/tiles/WebMercatorQuad/{z}/{x}/{y}.webp?${params}`
    );
}

let packingPromise = null;

/** The COG packing the backend reports, fetched once per page load. */
export function getReliefPacking() {
    packingPromise ??= (async () => {
        try {
            const res = await fetch(`${BACKEND_URL}/relief/packing`);
            if (res.ok) return await res.json();
            console.warn(`Relief packing request failed (${res.status}), using defaults`);
        } catch (err) {
            console.warn('Could not fetch relief packing metadata, using defaults:', err);
        }
        return FALLBACK_PACKING;
    })();
    return packingPromise;
}

/** The relief template for a display range in metres, packing resolved for you. */
export async function buildReliefTileUrl(
    vminMetres = layerDefaults.relief.vminMetres,
    vmaxMetres = layerDefaults.relief.vmaxMetres,
) {
    return reliefTileUrl(vminMetres, vmaxMetres, await getReliefPacking());
}

/** Quebec Public Land (PATP) WMS template. */
export function publicLandWmsUrl(base = QUEBEC_PUBLIC_LAND_WMS_URL) {
    return (
        base +
        '?SERVICE=WMS' +
        '&VERSION=1.3.0' +
        '&REQUEST=GetMap' +
        '&LAYERS=0' +
        '&STYLES=' +
        '&FORMAT=image/png' +
        '&TRANSPARENT=TRUE' +
        '&CRS=EPSG:3857' +
        '&WIDTH=256&HEIGHT=256' +
        '&BBOX={bbox-epsg-3857}'
    );
}
