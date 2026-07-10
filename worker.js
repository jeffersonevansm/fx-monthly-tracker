/**
 * FX Monthly Tracker -- native Cloudflare Worker app (no Streamlit).
 * Serves the frontend (index.html) and provides the data/AI API:
 *   GET  /api/pair?name=DXY      prices + monthly summary + technicals (Yahoo)
 *   GET  /api/news?category=forex   headlines, HTML-stripped (Finnhub)
 *   GET  /api/macro                 US macro series (FRED)
 *   POST /api/research {pair,month,search}   Claude research report (Anthropic)
 *
 * Secrets (Cloudflare dashboard -> this worker -> Settings -> Variables & Secrets):
 *   FINNHUB_API_KEY, FRED_API_KEY, ANTHROPIC_API_KEY
 * Optional var: RESEARCH_DISABLED = "1" to switch off the AI endpoint.
 */

import HTML from "./index.html";

const PAIRS = {
  "DXY":     { ticker: "DX-Y.NYB", usdBase: true },
  "EUR/USD": { ticker: "EURUSD=X", usdBase: false },
  "GBP/USD": { ticker: "GBPUSD=X", usdBase: false },
  "AUD/USD": { ticker: "AUDUSD=X", usdBase: false },
  "NZD/USD": { ticker: "NZDUSD=X", usdBase: false },
  "USD/IDR": { ticker: "USDIDR=X", usdBase: true },
};

const FRED_SERIES = {
  "Fed funds rate (%, level)": "FEDFUNDS",
  "CPI (index level)": "CPIAUCSL",
  "Core CPI (index level)": "CPILFESL",
  "Unemployment rate (%)": "UNRATE",
  "Nonfarm payrolls (000s)": "PAYEMS",
};

const CACHE_BASE = "https://cache.fx-monthly-tracker.internal";

// ============================ helpers ====================================

function json(data, status, sMaxAge) {
  const headers = { "content-type": "application/json; charset=utf-8" };
  if (sMaxAge) headers["cache-control"] = "s-maxage=" + sMaxAge;
  return new Response(JSON.stringify(data), { status: status || 200, headers });
}

async function withCache(ctx, key, producer) {
  const cache = caches.default;
  const req = new Request(CACHE_BASE + key);
  const hit = await cache.match(req);
  if (hit) return hit;
  const resp = await producer();
  if (resp.status === 200 && resp.headers.get("cache-control")) {
    ctx.waitUntil(cache.put(req, resp.clone()));
  }
  return resp;
}

function ymOf(unixSec) {
  const d = new Date(unixSec * 1000);
  const m = d.getUTCMonth() + 1;
  return d.getUTCFullYear() + "-" + (m < 10 ? "0" + m : "" + m);
}

// ============================ math =======================================

function sma(values, n) {
  const out = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= n) sum -= values[i - n];
    if (i >= n - 1) out[i] = sum / n;
  }
  return out;
}

function emaLast(values, span) {
  const a = 2 / (span + 1);
  let e = values[0];
  for (let i = 1; i < values.length; i++) e = a * values[i] + (1 - a) * e;
  return e;
}

function emaSeries(values, span) {
  const a = 2 / (span + 1);
  const out = [values[0]];
  for (let i = 1; i < values.length; i++) out.push(a * values[i] + (1 - a) * out[i - 1]);
  return out;
}

function rsiLast(closes, n) {
  n = n || 14;
  let up = 0, down = 0, init = false;
  const a = 1 / n;
  for (let i = 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    const u = d > 0 ? d : 0;
    const dn = d < 0 ? -d : 0;
    if (!init) { up = u; down = dn; init = true; continue; }
    up = a * u + (1 - a) * up;
    down = a * dn + (1 - a) * down;
  }
  if (down === 0) return up === 0 ? 50 : 100;
  return 100 - 100 / (1 + up / down);
}

function monthlySummary(t, o, h, l, c, usdBase) {
  const rows = [];
  let cur = null;
  for (let i = 0; i < t.length; i++) {
    const ym = ymOf(t[i]);
    if (!cur || cur.ym !== ym) {
      if (cur) rows.push(cur);
      cur = { ym: ym, open: c[i], close: c[i], high: h[i], low: l[i] };
    }
    cur.close = c[i];
    if (h[i] != null && h[i] > cur.high) cur.high = h[i];
    if (l[i] != null && l[i] < cur.low) cur.low = l[i];
  }
  if (cur) rows.push(cur);
  for (const r of rows) {
    r.chgPct = (r.close / r.open - 1) * 100;
    const strong = r.chgPct > 0;
    r.usdEnded = usdBase ? (strong ? "stronger" : "weaker") : (strong ? "weaker" : "stronger");
  }
  return rows.reverse(); // newest first
}

function technicalsAsOf(t, c, h, l, ym) {
  // index of last bar inside ym
  let end = -1;
  for (let i = 0; i < t.length; i++) if (ymOf(t[i]) <= ym) end = i;
  if (end < 30) return null;
  const tc = c.slice(0, end + 1);
  const th = h.slice(0, end + 1);
  const tl = l.slice(0, end + 1);
  const tt = t.slice(0, end + 1);
  const px = tc[tc.length - 1];

  const rsi = rsiLast(tc, 14);
  const rsiState = rsi >= 70 ? "Overbought" : rsi >= 55 ? "Bullish momentum" :
    rsi >= 45 ? "Neutral" : rsi >= 30 ? "Bearish momentum" : "Oversold";

  const macdSeries = [];
  const e12 = emaSeries(tc, 12), e26 = emaSeries(tc, 26);
  for (let i = 0; i < tc.length; i++) macdSeries.push(e12[i] - e26[i]);
  const signal = emaLast(macdSeries, 9);
  const sig9 = emaSeries(macdSeries, 9);
  const hist = macdSeries[macdSeries.length - 1] - signal;
  const histPrev = macdSeries[macdSeries.length - 2] - sig9[sig9.length - 2];
  const macdState = hist > 0
    ? ("Bullish — MACD above signal" + (hist > histPrev ? ", histogram expanding" : ", momentum fading"))
    : ("Bearish — MACD below signal" + (hist < histPrev ? ", histogram expanding" : ", momentum fading"));

  const smas = {};
  for (const n of [20, 50, 200]) {
    smas[n] = tc.length >= n ? sma(tc, n)[tc.length - 1] : null;
  }
  const mom3 = tc.length >= 63 ? (px / tc[tc.length - 63] - 1) * 100 : 0;
  let pts = 0;
  if (smas[50] && px > smas[50]) pts++;
  if (smas[200] && px > smas[200]) pts++;
  if (smas[50] && smas[200] && smas[50] > smas[200]) pts++;
  if (mom3 > 0) pts++;
  const trend = pts >= 3 ? "Uptrend" : pts <= 1 ? "Downtrend" : "Sideways / transitional";

  // structure from last 3 monthly highs/lows
  const mm = {};
  const order = [];
  for (let i = 0; i < tt.length; i++) {
    const k = ymOf(tt[i]);
    if (!mm[k]) { mm[k] = { H: th[i], L: tl[i] }; order.push(k); }
    if (th[i] != null && th[i] > mm[k].H) mm[k].H = th[i];
    if (tl[i] != null && tl[i] < mm[k].L) mm[k].L = tl[i];
  }
  let structure = "Range-bound / mixed";
  if (order.length >= 3) {
    const [a, b, cc] = order.slice(-3).map((k) => mm[k]);
    if (cc.H > b.H && b.H > a.H && cc.L > b.L && b.L > a.L) structure = "Higher highs · higher lows (bullish)";
    else if (cc.H < b.H && b.H < a.H && cc.L < b.L && b.L < a.L) structure = "Lower highs · lower lows (bearish)";
    else if (cc.L > b.L && cc.H < b.H) structure = "Compression — range tightening";
  }

  // pivots from the selected month + 3-month extremes
  let mh = null, ml = null, mc = px;
  for (let i = 0; i < tt.length; i++) {
    if (ymOf(tt[i]) === ym) {
      if (mh == null || th[i] > mh) mh = th[i];
      if (ml == null || tl[i] < ml) ml = tl[i];
      mc = tc[i];
    }
  }
  if (mh == null) { mh = px; ml = px; }
  const P = (mh + ml + mc) / 3;
  const rng = mh - ml;
  const qStart = Math.max(0, tt.length - 66);
  let qh = -Infinity, ql = Infinity;
  for (let i = qStart; i < tt.length; i++) {
    if (th[i] != null && th[i] > qh) qh = th[i];
    if (tl[i] != null && tl[i] < ql) ql = tl[i];
  }
  const levels = [
    ["R2 (pivot)", P + rng], ["R1 (pivot)", 2 * P - ml], ["Monthly pivot", P],
    ["S1 (pivot)", 2 * P - mh], ["S2 (pivot)", P - rng],
    ["3-month high", qh], ["3-month low", ql],
  ].sort((x, y) => y[1] - x[1]);

  return {
    px: px, rsi: rsi, rsiState: rsiState,
    macd: macdSeries[macdSeries.length - 1], macdSignal: signal, macdHist: hist,
    macdState: macdState, smas: smas, mom3: mom3, trend: trend,
    structure: structure, levels: levels,
  };
}

function technicalsToText(tech, dp) {
  if (!tech) return "(insufficient history for indicators)";
  const f = (v) => v == null ? "n/a" : Number(v).toFixed(dp);
  const smaTxt = [20, 50, 200].filter((n) => tech.smas[n]).map((n) => "SMA" + n + "=" + f(tech.smas[n])).join(", ");
  const lvTxt = tech.levels.map((x) => x[0] + "=" + f(x[1])).join("; ");
  return "Close=" + f(tech.px) + " | Trend: " + tech.trend + " (3m momentum " + tech.mom3.toFixed(2) + "%) | " +
    "RSI14=" + tech.rsi.toFixed(1) + " (" + tech.rsiState + ") | MACD=" + tech.macd.toFixed(5) +
    " vs signal " + tech.macdSignal.toFixed(5) + " (" + tech.macdState + ") | " + smaTxt +
    " | Structure: " + tech.structure + " | Key levels: " + lvTxt;
}

// ============================ text cleanup ===============================

const CITE_RE = /<\/?cite[^>]*>/g;
const TAG_RE = /<[^>]+>/g;

function cleanHtml(raw, maxLen) {
  if (!raw) return "";
  let text = raw.replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/gi, " ");
  text = text.replace(TAG_RE, " ");
  text = text.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#0?39;/g, "'").replace(/&nbsp;/g, " ");
  text = text.replace(/\s+/g, " ").trim();
  const cap = maxLen || 380;
  if (text.length > cap) {
    text = text.slice(0, cap);
    const sp = text.lastIndexOf(" ");
    if (sp > 0) text = text.slice(0, sp);
    text = text.replace(/[,.;:]+$/, "") + " …";
  }
  return text;
}

function cleanStrings(obj) {
  if (typeof obj === "string") return obj.replace(CITE_RE, "").replace(/\s+/g, " ").trim();
  if (Array.isArray(obj)) return obj.map(cleanStrings);
  if (obj && typeof obj === "object") {
    const out = {};
    for (const k of Object.keys(obj)) out[k] = cleanStrings(obj[k]);
    return out;
  }
  return obj;
}

// ============================ JSON repair ================================

function closeOpen(chunk) {
  const stack = [];
  let inStr = false, esc = false;
  for (const ch of chunk) {
    if (inStr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') inStr = false;
    } else if (ch === '"') inStr = true;
    else if (ch === "{") stack.push("}");
    else if (ch === "[") stack.push("]");
    else if ((ch === "}" || ch === "]") && stack.length) stack.pop();
  }
  if (inStr) chunk += '"';
  chunk = chunk.replace(/[,:\s]+$/, "");
  return chunk + stack.reverse().join("");
}

function repairJson(chunk) {
  for (let i = 0; i < 60; i++) {
    try { return JSON.parse(closeOpen(chunk)); } catch (e) { /* chop */ }
    const cut = Math.max(chunk.lastIndexOf(","), chunk.lastIndexOf("{"), chunk.lastIndexOf("["));
    if (cut <= 0) return null;
    chunk = chunk.slice(0, cut);
  }
  return null;
}

function extractJson(text) {
  text = (text || "").replace(/```(?:json)?/g, "").replace(CITE_RE, "");
  const s = text.indexOf("{");
  if (s === -1) return null;
  const e = text.lastIndexOf("}");
  if (e > s) {
    const chunk = text.slice(s, e + 1);
    for (const candidate of [chunk, chunk.replace(/,\s*([}\]])/g, "$1")]) {
      try { return cleanStrings(JSON.parse(candidate)); } catch (err) { /* next */ }
    }
  }
  const repaired = repairJson(text.slice(s));
  return repaired == null ? null : cleanStrings(repaired);
}

// ============================ upstream fetchers ==========================

async function yahooHistory(ticker) {
  const path = "/v8/finance/chart/" + encodeURIComponent(ticker) + "?range=2y&interval=1d";
  const headers = { "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) fx-monthly-tracker/1.0", "Accept": "application/json" };
  for (const host of ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]) {
    try {
      const r = await fetch("https://" + host + path, { headers: headers });
      if (!r.ok) continue;
      const j = await r.json();
      const res = j && j.chart && j.chart.result && j.chart.result[0];
      if (!res || !res.timestamp) continue;
      const q = res.indicators.quote[0];
      const t = [], o = [], h = [], l = [], c = [];
      for (let i = 0; i < res.timestamp.length; i++) {
        if (q.close[i] == null) continue;
        t.push(res.timestamp[i]);
        o.push(q.open[i] != null ? q.open[i] : q.close[i]);
        h.push(q.high[i] != null ? q.high[i] : q.close[i]);
        l.push(q.low[i] != null ? q.low[i] : q.close[i]);
        c.push(q.close[i]);
      }
      if (c.length > 30) return { t: t, o: o, h: h, l: l, c: c };
    } catch (e) { /* try next host */ }
  }
  return null;
}

async function pairPayload(pair) {
  const cfg = PAIRS[pair];
  const data = await yahooHistory(cfg.ticker);
  if (!data) return null;
  const months = monthlySummary(data.t, data.o, data.h, data.l, data.c, cfg.usdBase);
  const tech = {};
  for (const row of months.slice(0, 14)) {
    tech[row.ym] = technicalsAsOf(data.t, data.c, data.h, data.l, row.ym);
  }
  return {
    pair: pair,
    candles: data,
    sma20: sma(data.c, 20),
    sma50: sma(data.c, 50),
    months: months,
    tech: tech,
  };
}

// ============================ routes =====================================

async function routePair(url, env, ctx) {
  const pair = url.searchParams.get("name");
  if (!PAIRS[pair]) return json({ error: "unknown_pair" }, 400);
  return withCache(ctx, "/pair/" + encodeURIComponent(pair), async () => {
    const payload = await pairPayload(pair);
    if (!payload) return json({ error: "prices_unavailable" }, 502);
    return json(payload, 200, 3600);
  });
}

async function routeNews(url, env, ctx) {
  if (!env.FINNHUB_API_KEY) return json({ error: "no_key" });
  const cat = url.searchParams.get("category") || "forex";
  if (!["forex", "general", "crypto", "merger"].includes(cat)) return json({ error: "bad_category" }, 400);
  return withCache(ctx, "/news/" + cat, async () => {
    const r = await fetch("https://finnhub.io/api/v1/news?category=" + cat + "&token=" + env.FINNHUB_API_KEY);
    if (!r.ok) return json({ error: "news_unavailable (" + r.status + ")" }, 502);
    const items = (await r.json()).slice(0, 25).map((n) => ({
      headline: n.headline || "(no title)",
      url: n.url || "#",
      source: n.source || "",
      datetime: n.datetime || 0,
      summary: cleanHtml(n.summary || ""),
    }));
    return json({ items: items }, 200, 900);
  });
}

async function routeMacro(env, ctx) {
  if (!env.FRED_API_KEY) return json({ error: "no_key" });
  return withCache(ctx, "/macro", async () => {
    const start = new Date(Date.now() - 20 * 31 * 86400 * 1000).toISOString().slice(0, 10);
    const out = {};
    await Promise.all(Object.entries(FRED_SERIES).map(async ([label, sid]) => {
      try {
        const r = await fetch("https://api.stlouisfed.org/fred/series/observations?series_id=" + sid +
          "&api_key=" + env.FRED_API_KEY + "&file_type=json&observation_start=" + start + "&sort_order=asc");
        const obs = (await r.json()).observations || [];
        out[label] = obs.filter((x) => x.value !== "." && x.value !== "").map((x) => [x.date.slice(0, 7), x.value]);
      } catch (e) { out[label] = []; }
    }));
    return json({ data: out }, 200, 21600);
  });
}

function macroToText(macro) {
  if (!macro || macro.error) return "(no US economic data -- FRED key not set)";
  const lines = [];
  for (const [label, series] of Object.entries(macro.data || {})) {
    if (series.length) lines.push(label + " -> " + series.slice(-8).map((x) => x[0] + ": " + x[1]).join(", "));
  }
  return lines.join("\n") || "(no US economic data returned)";
}

const REPORT_SCHEMA = `{
 "headline": "bank-style report title, <= 12 words, no pair prefix",
 "executive_summary": "120-170 word past-tense review of the month for this pair",
 "macro_drivers": [3-5 items: {"country_code":"US","title":"...","impact":"bullish|bearish|mixed","analysis":"1-3 sentences, causal"}],
 "key_events": [4-8 items, chronological: {"date":"Jun 18","country_code":"US","event":"FOMC decision","actual":"","forecast":"","previous":"","impact":"high|medium|low","analysis":"1-2 sentences on the market reaction"}],
 "fundamental_view": "3-5 sentences: policy divergence, rates, inflation, growth",
 "technical_view": "3-5 sentences grounded in the indicator readout provided",
 "sentiment_view": "3-5 sentences: positioning, risk appetite, prevailing narrative",
 "risk_factors": [2-4 items: {"title":"...","detail":"1-2 sentences","severity":"high|medium|low"}],
 "outlook": {"bias":"Bullish|Neutral|Bearish","confidence":55,"narrative":"4-6 sentence forward view for next month","key_drivers":["...","..."],"next_month_risks":["...","..."]}
}`;

function monthLabel(ym) {
  const names = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];
  return names[parseInt(ym.slice(5), 10) - 1] + " " + ym.slice(0, 4);
}

async function routeResearch(request, env, ctx) {
  if (env.RESEARCH_DISABLED === "1") return json({ error: "disabled" }, 403);
  if (!env.ANTHROPIC_API_KEY) return json({ error: "no_key" });
  let body;
  try { body = await request.json(); } catch (e) { return json({ error: "bad_request" }, 400); }
  const pair = body.pair, ym = body.month;
  const useSearch = body.search === true;
  if (!PAIRS[pair] || !/^\d{4}-(0[1-9]|1[0-2])$/.test(ym || "")) return json({ error: "bad_request" }, 400);

  const cacheKey = "/research/" + encodeURIComponent(pair) + "/" + ym + "/" + (useSearch ? "s1" : "s0");
  const cache = caches.default;
  const hit = await cache.match(new Request(CACHE_BASE + cacheKey));
  if (hit) return hit;

  // build contexts server-side
  const payload = await pairPayload(pair);
  if (!payload) return json({ error: "prices_unavailable" }, 502);
  const idx = payload.months.findIndex((m) => m.ym === ym);
  if (idx === -1) return json({ error: "month_out_of_range" }, 400);
  const dp = pair === "USD/IDR" ? 0 : pair === "DXY" ? 2 : 4;
  const rows = payload.months.slice(Math.max(0, idx - 1), idx + 5);
  const priceCtx = rows.map((r) =>
    r.ym + "  open=" + r.open.toFixed(dp) + "  close=" + r.close.toFixed(dp) +
    "  chg=" + r.chgPct.toFixed(2) + "%  high=" + r.high.toFixed(dp) +
    "  low=" + r.low.toFixed(dp) + "  USD ended " + r.usdEnded).join("\n");
  const techCtx = technicalsToText(payload.tech[ym], dp);

  let macroCtx = "(no US economic data -- FRED key not set)";
  if (env.FRED_API_KEY) {
    try { macroCtx = macroToText(await (await routeMacro(env, ctx)).json()); } catch (e) { /* keep default */ }
  }
  let newsCtx = "";
  const recentCut = new Date(Date.now() - 62 * 86400 * 1000).toISOString().slice(0, 7);
  if (env.FINNHUB_API_KEY && ym >= recentCut) {
    try {
      const news = await (await routeNews(new URL("https://x/api/news?category=forex"), env, ctx)).json();
      newsCtx = (news.items || []).slice(0, 10).map((n) => "- " + n.headline).join("\n");
    } catch (e) { /* optional */ }
  }

  const label = monthLabel(ym);
  const sourceInstr = useSearch
    ? "Use web search to verify the actual dated events of this month for this pair (central-bank decisions, CPI/NFP prints, geopolitical shocks) and fill in real actual/forecast/previous figures where you find them."
    : "No web access: derive events from the provided data matrices and well-known recurring calendar patterns (FOMC, CPI, NFP weeks). Only include events you are confident about; leave actual/forecast/previous as \"\" when unsure. Do not invent figures.";
  const prompt =
    "You are a senior macro FX strategist at a global investment bank writing the monthly research report on " +
    pair + " for " + label + ". Analyze the month through three lenses: FUNDAMENTAL (central bank policy, rate " +
    "differentials, inflation, growth, employment), TECHNICAL (use the indicator readout provided; discuss trend, " +
    "momentum and key levels), and SENTIMENT (positioning, risk appetite, dominant market narrative).\n\n" +
    sourceInstr + "\n\n" +
    "Respond with ONLY one valid JSON object -- no markdown fences, no commentary -- exactly this schema:\n" +
    REPORT_SCHEMA + "\n\n" +
    "Rules: \"bias\" is the direction of " + pair + " itself next month. \"confidence\" is an integer 0-100. " +
    "Event dates must fall inside " + label + ". country_code is ISO-2 (US, EU, GB, AU, NZ, ID...). " +
    "Be specific and causal; institutional tone; no filler. NEVER put <cite> tags, citation markers, footnotes " +
    "or URLs inside JSON strings. Write no prose before or after the JSON object.\n\n" +
    "PRICE ACTION MATRIX (monthly):\n" + priceCtx + "\n\n" +
    "TECHNICAL READOUT (as of " + label + " close):\n" + techCtx + "\n\n" +
    "US MACRO DATA (FRED):\n" + macroCtx + "\n\n" +
    "RECENT MARKET HEADLINES (sentiment context):\n" + (newsCtx || "(none provided)");

  const apiBody = {
    model: "claude-haiku-4-5-20251001",
    max_tokens: 8000,
    messages: [{ role: "user", content: prompt }],
  };
  if (useSearch) apiBody.tools = [{ type: "web_search_20250305", name: "web_search", max_uses: 5 }];

  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": env.ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify(apiBody),
  });
  if (!r.ok) {
    let detail = "";
    try { detail = (await r.json()).error.message; } catch (e) { /* opaque */ }
    return json({ error: "ai_error (" + r.status + ") " + detail });
  }
  const msg = await r.json();
  let raw = "";
  const sources = [];
  const seen = new Set();
  for (const block of msg.content || []) {
    if (block.type === "text") {
      raw += block.text;
      for (const c of block.citations || []) {
        if (c.url && !seen.has(c.url)) { seen.add(c.url); sources.push([c.title || c.url, c.url]); }
      }
    }
  }
  const report = extractJson(raw);
  const resp = json({ report: report, raw: raw.slice(0, 20000), sources: sources }, 200,
    report ? 86400 : undefined);
  if (report) ctx.waitUntil(cache.put(new Request(CACHE_BASE + cacheKey), resp.clone()));
  return resp;
}

// ============================ entry ======================================

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const p = url.pathname;
    try {
      if (p === "/api/pair") return await routePair(url, env, ctx);
      if (p === "/api/news") return await routeNews(url, env, ctx);
      if (p === "/api/macro") return await routeMacro(env, ctx);
      if (p === "/api/research" && request.method === "POST") return await routeResearch(request, env, ctx);
      if (p === "/api/status") {
        return json({
          prices: true,
          news: !!env.FINNHUB_API_KEY,
          macro: !!env.FRED_API_KEY,
          ai: !!env.ANTHROPIC_API_KEY && env.RESEARCH_DISABLED !== "1",
        });
      }
      if (p.startsWith("/api/")) return json({ error: "not_found" }, 404);
      return new Response(HTML, {
        headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-cache" },
      });
    } catch (e) {
      return json({ error: String((e && e.message) || e) }, 500);
    }
  },
};
