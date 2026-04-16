const WMS_TARGET = 'https://servicescarto.mern.gouv.qc.ca/pes/services/Territoire/PATP_prov_WMS/MapServer/WMSServer';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/patp-wms') {
      const target = new URL(WMS_TARGET);
      target.search = url.search;

      const wmsResponse = await fetch(target.toString(), { method: request.method });

      const headers = new Headers(wmsResponse.headers);
      headers.set('Access-Control-Allow-Origin', '*');

      return new Response(wmsResponse.body, {
        status: wmsResponse.status,
        headers,
      });
    }

    // All other requests: serve static assets
    return env.ASSETS.fetch(request);
  },
};
