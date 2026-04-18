import { defineConfig } from 'vite';

import { cloudflare } from "@cloudflare/vite-plugin";

export default defineConfig({
  server: {
    host: '0.0.0.0',   // bind to 0.0.0.0 so the Vite container is reachable
    port: 5173,
    proxy: {
      // Only proxied route: WMS CORS workaround (no auth, no env var needed)
      '/patp-wms': {
        target: 'https://servicescarto.mern.gouv.qc.ca',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/patp-wms/, '/pes/services/Territoire/PATP_prov_WMS/MapServer/WMSServer'),
      },
    },
  },
  plugins: [cloudflare({ workerEntrypoint: './src/worker.js' })]
});