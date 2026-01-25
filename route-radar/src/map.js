
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

// Export a function to build the HRDEM WMS URL
export function buildHRDEMWmsUrl({style = 'slope_grey'} = {}) {
    return `https://datacube.services.geo.ca/wrapper/ogc/elevation-hrdem-mosaic?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=dtm-slope&STYLES=${style}&FORMAT=image/png&TRANSPARENT=TRUE&CRS=EPSG:3857&WIDTH=512&HEIGHT=512&BBOX={bbox-epsg-3857}`;
}

export function initMap() {
    const quebecImageryUrl = "https://servicesmatriciels.mern.gouv.qc.ca/erdas-iws/ogc/wmts/Imagerie_Continue/Imagerie_GQ/default/GoogleMapsCompatibleExt2:epsg:3857/{z}/{y}/{x}.jpg";
    const cartoLabelsUrl = "https://basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}.png";

    // Use the shared builder for the HRDEM WMS URL
    const hrdemWmsUrl = buildHRDEMWmsUrl();

    const map = new maplibregl.Map({
        container: 'map',
        style: {
            version: 8,
            sources: {
                'quebec-imagery': { type: 'raster', tiles: [quebecImageryUrl], tileSize: 256 },
                'map-labels': { type: 'raster', tiles: [cartoLabelsUrl], tileSize: 256 },
                // Add the National HRDEM WMS
                'hrdem-wms': {
                    type: 'raster',
                    tiles: [hrdemWmsUrl],
                    tileSize: 256
                }
            },
            layers: [
                { id: 'base-imagery', type: 'raster', source: 'quebec-imagery' },
                {
                    id: 'hrdem-wms-layer',
                    type: 'raster',
                    source: 'hrdem-wms',
                    paint: {
                        'raster-opacity': 0.4,
                        // This "tints" the dark/light areas to simulate a colormap
                        'raster-hue-rotate': 180,
                        'raster-saturation': -0.3,
                        'raster-contrast': 0.1
                    }
                },
                { id: 'labels-layer', type: 'raster', source: 'map-labels' }
            ]
        },
        center: [-74.2, 46.0],
        zoom: 12
    });

    return map;
}