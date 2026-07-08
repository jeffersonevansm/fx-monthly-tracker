/**
 * Cloudflare Worker: serves the Streamlit Cloud app on a custom domain.
 *
 * Streamlit Community Cloud bounces new visitors through a cookie handshake
 * on share.streamlit.io that only accepts its own *.streamlit.app URLs. This
 * worker performs that handshake server-side and relays the session cookies
 * to the visitor, so the app loads transparently on this domain.
 *
 * If the Streamlit app URL ever changes, update UPSTREAM below.
 */

const UPSTREAM = "fx-monthly-analysis.streamlit.app";
const AUTH_HOST = "share.streamlit.io";
const MAX_HOPS = 6;

const cookiePair = (setCookie) => setCookie.split(";", 1)[0].trim();

/** Remove the Domain attribute so the cookie binds to the visitor's domain. */
function stripDomain(setCookie) {
  return setCookie
    .split(";")
    .filter((part) => !/^\s*domain\s*=/i.test(part))
    .join(";");
}

/** Merge a Cookie header string with new Set-Cookie values into one jar. */
function jarWith(jar, setCookies) {
  const map = new Map();
  const add = (pair) => {
    const eq = pair.indexOf("=");
    if (eq > 0) map.set(pair.slice(0, eq).trim(), pair.slice(eq + 1).trim());
  };
  (jar || "").split(";").map((s) => s.trim()).filter(Boolean).forEach(add);
  setCookies.forEach((sc) => add(cookiePair(sc)));
  return [...map.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
}

function getSetCookies(response) {
  if (typeof response.headers.getSetCookie === "function") {
    return response.headers.getSetCookie();
  }
  const single = response.headers.get("Set-Cookie");
  return single ? [single] : [];
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const publicHost = url.hostname;
    url.protocol = "https:";
    url.hostname = UPSTREAM;
    url.port = "";

    // Forward the request with headers rewritten so upstream accepts it and
    // never learns the public hostname (it builds redirects from these).
    const headers = new Headers(request.headers);
    headers.set("Origin", `https://${UPSTREAM}`);
    headers.set("X-Forwarded-Host", UPSTREAM);
    headers.set("X-Forwarded-Proto", "https");
    headers.delete("X-Forwarded-For");
    const referer = headers.get("Referer");
    if (referer) headers.set("Referer", referer.replaceAll(publicHost, UPSTREAM));

    let response = await fetch(new Request(url.toString(), {
      method: request.method,
      headers,
      body: request.body,
      redirect: "manual",
    }));

    // WebSocket upgrade (Streamlit's live connection): hand back untouched.
    if (response.status === 101) return response;

    // Follow Streamlit Cloud's auth/cookie handshake server-side instead of
    // exposing the visitor to share.streamlit.io (which rejects our domain).
    const collected = [...getSetCookies(response)];
    let jar = jarWith(request.headers.get("Cookie"), collected);
    let hops = 0;
    while ([301, 302, 303, 307, 308].includes(response.status) && hops < MAX_HOPS) {
      hops += 1;
      const location = response.headers.get("Location");
      if (!location) break;
      const next = new URL(location, `https://${UPSTREAM}/`);
      if (next.hostname === AUTH_HOST) {
        const ru = next.searchParams.get("redirect_uri");
        if (ru) next.searchParams.set("redirect_uri", ru.replaceAll(publicHost, UPSTREAM));
      } else if (next.hostname === publicHost || next.hostname === UPSTREAM) {
        next.hostname = UPSTREAM;
      } else {
        break; // redirect to an unrelated site -- pass through to the browser
      }
      const hopHeaders = new Headers();
      hopHeaders.set("User-Agent", request.headers.get("User-Agent") || "Mozilla/5.0");
      hopHeaders.set("Accept", request.headers.get("Accept") || "text/html,*/*");
      if (jar) hopHeaders.set("Cookie", jar);
      response = await fetch(next.toString(), { headers: hopHeaders, redirect: "manual" });
      const fresh = getSetCookies(response);
      collected.push(...fresh);
      jar = jarWith(jar, fresh);
    }

    // Rebuild headers: cookies re-scoped to our domain, redirects mapped back.
    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("Set-Cookie");
    const location = responseHeaders.get("Location");
    if (location) {
      responseHeaders.set("Location", location.replaceAll(UPSTREAM, publicHost));
    }
    for (const sc of collected) responseHeaders.append("Set-Cookie", stripDomain(sc));

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  },
};
