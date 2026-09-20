import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { toTilerUrl, registerTilerProtocol } from './tilerProtocol.js';

const HTTPS_URL = 'https://backend.test/mosaicjson/tiles/1/2/3.webp?rescale=0,350';

/** The handler MapLibre would have registered, plus the scheme it answers to. */
function captureHandler() {
    let scheme, handler;
    registerTilerProtocol({ addProtocol: (s, h) => { scheme = s; handler = h; } });
    return { scheme, handler };
}

const tile = (status, body = new ArrayBuffer(8)) => ({
    status,
    ok: status >= 200 && status < 300,
    arrayBuffer: async () => body,
});

describe('the tiler protocol handler', () => {
    let fetch;

    beforeEach(() => {
        vi.useFakeTimers();
        fetch = vi.fn();
        vi.stubGlobal('fetch', fetch);
    });
    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    /** Run `handler` to completion, letting every back-off wait elapse instantly. */
    function settle(promise) {
        // Claim the rejection now — the timers run before the caller can await.
        promise.catch(() => {});
        return vi.runAllTimersAsync().then(() => promise);
    }

    it('retries a 503 until the tile arrives, fetching the https url behind the scheme', async () => {
        const body = new ArrayBuffer(8);
        fetch.mockResolvedValueOnce(tile(503))
             .mockResolvedValueOnce(tile(503))
             .mockResolvedValueOnce(tile(200, body));

        const { handler } = captureHandler();
        const result = await settle(handler({ url: toTilerUrl(HTTPS_URL) }, new AbortController()));

        expect(result).toEqual({ data: body });
        expect(fetch).toHaveBeenCalledTimes(3);
        expect(fetch.mock.calls[0][0]).toBe(HTTPS_URL);
    });

    it('gives up rather than retrying a 503 forever', async () => {
        fetch.mockResolvedValue(tile(503));

        const { handler } = captureHandler();
        await expect(settle(handler({ url: toTilerUrl(HTTPS_URL) }, new AbortController())))
            .rejects.toThrow('503');
        expect(fetch.mock.calls.length).toBeLessThan(10);
    });

    it('does not retry a failure the backend will keep repeating', async () => {
        fetch.mockResolvedValue(tile(404));

        const { handler } = captureHandler();
        await expect(settle(handler({ url: toTilerUrl(HTTPS_URL) }, new AbortController())))
            .rejects.toThrow('404');
        expect(fetch).toHaveBeenCalledTimes(1);
    });

    it('drops a tile the map has already navigated away from', async () => {
        const abortController = new AbortController();
        abortController.abort();

        const { handler } = captureHandler();
        await expect(settle(handler({ url: toTilerUrl(HTTPS_URL) }, abortController)))
            .rejects.toThrow(/abort/i);
        expect(fetch).not.toHaveBeenCalled();
    });
});
