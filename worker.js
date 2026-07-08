/**
 * Cloudflare Worker: reverse proxy that serves the Streamlit Cloud app
 * on a custom domain. Attach your domain to this worker in the Cloudflare
 * dashboard (Workers & Pages -> this worker -> Settings -> Domains & Routes).
 *
 * Note: this proxies https://fx-monthly-analysis.streamlit.app -- if the
 * Streamlit app URL ever changes, update UPSTREAM below.
 */

const UPSTREAM = "fx-monthly-analysis.streamlit.app";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const publicHost = url.hostname;
    url.protocol = "https:";
    url.hostname = UPSTREAM;
    url.port = "";

    // Forward the request with headers rewritten so upstream accepts it.
    const headers = new Headers(request.headers);
    headers.set("Origin", `https://${UPSTREAM}`);
    const referer = headers.get("Referer");
    if (referer) headers.set("Referer", referer.replaceAll(publicHost, UPSTREAM));

    const upstreamRequest = new Request(url.toString(), {
      method: request.method,
      headers,
      body: request.body,
      redirect: "manual",
    });

    const response = await fetch(upstreamRequest);

    // WebSocket upgrade (Streamlit's live connection): hand back untouched.
    if (response.status === 101) return response;

    // Rewrite any redirects that point at the upstream host back to our domain.
    const responseHeaders = new Headers(response.headers);
    const location = responseHeaders.get("Location");
    if (location) {
      responseHeaders.set("Location", location.replaceAll(UPSTREAM, publicHost));
    }

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  },
};
