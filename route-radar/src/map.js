import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

// Define your AOI bounding box (example: Laurentides region)
// Exported for use in other modules if needed
export const aoiBounds = [
    [-76.15, 45.32], // Southwest corner [lng, lat]
    [-73.05, 46.44]  // Northeast corner [lng, lat]
];

// Export a function to build the HRDEM WMS URL
export function buildHRDEMWmsUrl(zFactor = 5, rescale = null) {
    let url = "https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic?SERVICE=WMS" +
        "&VERSION=1.3.0" +
        "&REQUEST=GetMap" +
        "&LAYERS=dtm-slope" +
        "&STYLES=slope_grey" +
        "&FORMAT=image/png" +
        "&TRANSPARENT=TRUE" +
        "&CRS=EPSG:3857" +
        "&WIDTH=256&HEIGHT=256" +
        "&BBOX={bbox-epsg-3857}" +
        `&zFactor=${zFactor}`; // Added zFactor for slope scaling

    // If you want to use the RGB Rescale parameters from the ExtendedCapabilities:
    if (rescale) {
        url += `&rescaleNewMinRed=${rescale.min}&rescaleNewMaxRed=${rescale.max}` +
               `&rescaleNewMinGreen=${rescale.min}&rescaleNewMaxGreen=${rescale.max}` +
               `&rescaleNewMinBlue=${rescale.min}&rescaleNewMaxBlue=${rescale.max}`;
    }

    return url;
}

// Export a function to build the COG tile URL for Titiler
export function buildCogTileUrl({colormap = 'cividis', rescale = '100,600'} = {}) {
    let url = 'http://localhost:8080/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=/cogs/laurentides_merged.tif';
    if (rescale) url += `&rescale=${encodeURIComponent(rescale)}`;
    if (colormap) url += `&colormap_name=${encodeURIComponent(colormap)}`;
    return url;
}

export function initMap() {
    const quebecImageryUrl = "https://servicesmatriciels.mern.gouv.qc.ca/erdas-iws/ogc/wmts/Imagerie_Continue/Imagerie_GQ/default/GoogleMapsCompatibleExt2:epsg:3857/{z}/{y}/{x}.jpg";
    const cartoLabelsUrl = "https://basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png";
    const cogTileUrl = buildCogTileUrl({});
    // Bounds from laurentides.geojson polygon
    // [[-74.30994776313827, 46.07484617926616], [-74.30994776313827, 45.85327435249255], [-74.05654223402449, 45.85327435249255], [-74.05654223402449, 46.07484617926616], [-74.30994776313827, 46.07484617926616]]
    const laurentidesBounds = [
        -74.30994776313827, // minX (west)
        45.85327435249255,  // minY (south)
        -74.05654223402449, // maxX (east)
        46.07484617926616   // maxY (north)
    ];

    // Convert AOI bounds from EPSG:4326 (lng/lat) to EPSG:3857 (Web Mercator)
    function lngLatTo3857(lng, lat) {
        const R = 6378137.0;
        const x = R * lng * Math.PI / 180;
        const y = R * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
        return [x, y];
    }
    const min3857 = lngLatTo3857(aoiBounds[0][0], aoiBounds[0][1]);
    const max3857 = lngLatTo3857(aoiBounds[1][0], aoiBounds[1][1]);
    const aoiBounds3857 = [min3857, max3857];

    // Use the shared builder for the HRDEM WMS URL, passing AOI bounds in EPSG:3857
    const hrdemWmsUrl = buildHRDEMWmsUrl(aoiBounds3857);

    const map = new maplibregl.Map({
        container: 'map',
        style: {
            version: 8,
            sources: {
                'quebec-imagery': { type: 'raster', tiles: [quebecImageryUrl], tileSize: 256 },
                'map-labels': { type: 'raster', tiles: [cartoLabelsUrl], tileSize: 256 },
                'hrdem-wms': {
                    type: 'raster',
                    tiles: [hrdemWmsUrl],
                    tileSize: 256
                },
                'local-cog': { 
                    type: 'raster',
                    tiles: [cogTileUrl],
                    tileSize: 256,
                    bounds: laurentidesBounds
                }
            },
            layers: [
                { id: 'base-imagery', type: 'raster', source: 'quebec-imagery' },
                { 
                    id: 'local-cog-layer',
                    type: 'raster',
                    source: 'local-cog',
                    paint: { 
                        'raster-opacity': 0.8 
                    } 
                },
                {
                    id: 'hrdem-wms-layer',
                    type: 'raster',
                    source: 'hrdem-wms',
                    paint: {
                        'raster-opacity': 0.7,
                    }
                },
                { id: 'labels-layer', type: 'raster', source: 'map-labels' },

            ]
        },
        center: [-74.19, 46.03],
        zoom: 14,
        maxBounds: aoiBounds // <-- Restrict map to AOI
    });

    return map;
}