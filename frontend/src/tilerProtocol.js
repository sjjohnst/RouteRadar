// The "tiler://" scheme: backend tile fetches that retry HTTP 503 with
// exponential back-off, because the tiler runs on Lambda without provisioned
// concurrency and sheds load during a cold-start burst.
//
// MapLibre's addProtocol intercepts the fetch for a single tile and lets us
// resolve it ourselves, so only the failing tile is retried — the rest of the
// source cache is untouched.
//
// The scheme name lives here, alongside the handler that answers to it.
// addProtocol dispatches purely on the URL scheme, so tile URLs are written
// through toTilerUrl() rather than pointing straight at https.
const SCHEME = 'tiler';

/** `https://host/…` → `tiler://host/…` */
export function toTilerUrl(httpsUrl) {
    return httpsUrl.replace(/^https:\/\//, `${SCHEME}://`);
}

/** @param {typeof import('maplibre-gl')} maplibregl */
export function registerTilerProtocol(maplibregl) {
    maplibregl.addProtocol(SCHEME, async (params, abortController) => {
        const url = params.url.replace(new RegExp(`^${SCHEME}://`), 'https://');

        let delay = 400; // ms — initial back-off
        const maxRetries = 4;

        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            if (abortController.signal.aborted) {
                throw new DOMException('Tile fetch aborted', 'AbortError');
            }
            const res = await fetch(url, { signal: abortController.signal });
            if (res.status !== 503 || attempt === maxRetries) {
                if (!res.ok) throw new Error(`Tile fetch failed: ${res.status}`);
                const data = await res.arrayBuffer();
                return { data };
            }
            // 503 — wait with jitter before retrying
            await new Promise((r) => setTimeout(r, delay + Math.random() * delay));
            delay = Math.min(delay * 2, 3000);
        }
    });
}
