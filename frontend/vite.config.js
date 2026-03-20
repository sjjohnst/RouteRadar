import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: '0.0.0.0',   // must bind to 0.0.0.0 inside Docker
    port: 5173,
    proxy: {
      // Forward all backend routes to the titiler container
      '/mosaicjson': { target: 'http://backend:8000', changeOrigin: true },
      '/relief':     { target: 'http://backend:8000', changeOrigin: true },
      '/cog':        { target: 'http://backend:8000', changeOrigin: true },
    },
  },
});
