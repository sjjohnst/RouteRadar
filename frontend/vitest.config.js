import { defineConfig } from 'vitest/config';

// Standalone from vite.config.js: the Cloudflare plugin rejects the Node
// externals Vitest injects, and tests never build the worker anyway.
export default defineConfig({
    test: {
        include: ['src/**/*.test.js'],
        env: { VITE_BACKEND_URL: 'https://backend.test' },
    },
});
