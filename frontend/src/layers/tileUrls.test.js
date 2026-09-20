import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { reliefTileUrl, FALLBACK_PACKING } from './tileUrls.js';

const params = (url) => new URLSearchParams(url.split('?')[1]);

describe('reliefTileUrl', () => {
    it('converts metres to packed DN using the scale factor', () => {
        const url = reliefTileUrl(0, 3.5, { scale_factor: 0.01, add_offset: 0 });
        expect(params(url).get('rescale')).toBe('0,350');
    });

    it('rounds the float noise the division leaves behind', () => {
        // 0.29 / 0.01 is 28.999999999999996 in IEEE 754, and DN are integers.
        const url = reliefTileUrl(0, 0.29, { scale_factor: 0.01, add_offset: 0 });
        expect(params(url).get('rescale')).toBe('0,29');
    });

    it('subtracts the offset before scaling', () => {
        const url = reliefTileUrl(1, 2, { scale_factor: 0.5, add_offset: 1 });
        expect(params(url).get('rescale')).toBe('0,2');
    });

    it('asks for webp over the tiler scheme so 503s can be retried per tile', () => {
        const url = reliefTileUrl(0, 1, FALLBACK_PACKING);
        expect(url.startsWith('tiler://')).toBe(true);
        expect(url).toContain('/{z}/{x}/{y}.webp?');
    });
});

describe('getReliefPacking', () => {
    let warn;

    beforeEach(() => {
        vi.resetModules();
        warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    });
    afterEach(() => vi.restoreAllMocks());

    const load = () => import('./tileUrls.js');

    it('fetches the packing metadata once, however many callers ask', async () => {
        const packing = { scale_factor: 0.02, add_offset: -5 };
        const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => packing });
        vi.stubGlobal('fetch', fetch);

        const { getReliefPacking } = await load();
        const [a, b] = await Promise.all([getReliefPacking(), getReliefPacking()]);

        expect(await getReliefPacking()).toEqual(packing);
        expect(a).toEqual(packing);
        expect(b).toEqual(packing);
        expect(fetch).toHaveBeenCalledTimes(1);
    });

    it('falls back to the ingestion default and says so when the fetch throws', async () => {
        vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

        const { getReliefPacking } = await load();

        expect(await getReliefPacking()).toEqual(FALLBACK_PACKING);
        expect(warn).toHaveBeenCalled();
    });

    it('falls back and says so when the backend answers with an error', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }));

        const { getReliefPacking } = await load();

        expect(await getReliefPacking()).toEqual(FALLBACK_PACKING);
        expect(warn).toHaveBeenCalled();
    });
});
