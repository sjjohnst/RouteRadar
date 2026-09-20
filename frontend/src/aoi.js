// The area of interest: the geographic envelope the map is locked to.
//
// Transcribed from public/aoi/laurentides.geojson, deleted in the same commit
// that added these constants.
// Re-derive with a GIS tool and paste here if the extent changes.

/** [minLng, minLat, maxLng, maxLat] — longitude first, as GeoJSON orders it. */
export const AOI_BBOX = [
    -76.15321265252634, 45.31853048608002,
    -73.0522774708293, 46.437968417966374,
];

/** The same envelope as MapLibre corner pairs, for `maxBounds` and `bounds`. */
export const AOI_BOUNDS = [
    [AOI_BBOX[0], AOI_BBOX[1]],
    [AOI_BBOX[2], AOI_BBOX[3]],
];

/** Is [lng, lat] inside the AOI? Edges count as inside. */
export function containsPoint([lng, lat]) {
    const [minLng, minLat, maxLng, maxLat] = AOI_BBOX;
    return lng >= minLng && lng <= maxLng && lat >= minLat && lat <= maxLat;
}
