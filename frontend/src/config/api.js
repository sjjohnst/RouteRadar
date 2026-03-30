// src/config/api.js
// Central place to configure backend API URL for dev/prod

// Quebec Public Land WMS URL: use env variable in prod, else default
export const QUEBEC_PUBLIC_LAND_WMS_URL =
    import.meta.env.VITE_QUEBEC_PUBLIC_LAND_WMS_URL ||
    "https://servicescarto.mern.gouv.qc.ca/pes/services/Territoire/PATP_prov_WMS/MapServer/WMSServer";

// Use environment variable if available, else fallback to default
export const BACKEND_URL =
    window.BACKEND_URL ||
    import.meta.env.VITE_BACKEND_URL ||
    'https://165.245.234.224.sslip.io'; // DigitalOcean default

// Quebec Imagery URL: use env variable in prod, else default
export const QUEBEC_IMAGERY_URL =
    import.meta.env.VITE_QUEBEC_IMAGERY_URL ||
    "https://servicesmatriciels.mern.gouv.qc.ca/erdas-iws/ogc/wmts/Imagerie_Continue/Imagerie_GQ/default/GoogleMapsCompatibleExt2:epsg:3857/{z}/{y}/{x}.jpg";
