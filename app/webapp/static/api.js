import { setLang } from "./i18n.js";

export const tg = window.Telegram && window.Telegram.WebApp;
export const state = {
  token: "",
  tokenExp: 0,
  me: null,
  dash: null,
};

const BRAND = "#0f172a";
const STORE_KEY = "ritm.snapshot.v3"; // last dashboard only; the session token stays in memory
const cache = new Map();
const inflight = new Map();
let signingIn = null;

export function applyTheme() {
  if (!tg) {
    document.documentElement.dataset.theme = "dark";
    return;
  }
  tg.ready();
  tg.expand();
  const scheme = tg.colorScheme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = scheme;
  const bg = scheme === "light" ? "#f1f5f9" : BRAND;
  try {
    tg.setHeaderColor(bg);
    tg.setBackgroundColor(bg);
  } catch (_err) {
    /* Older Telegram clients may lack color helpers. */
  }
  if (tg.onEvent && !applyTheme.bound) {
    applyTheme.bound = true;
    tg.onEvent("themeChanged", () => applyTheme());
  }
}

export function haptic(style = "light") {
  const feedback = tg && tg.HapticFeedback;
  if (!feedback) return;
  try {
    if (style === "success" && feedback.notificationOccurred) {
      feedback.notificationOccurred("success");
      return;
    }
    if (style === "error" && feedback.notificationOccurred) {
      feedback.notificationOccurred("error");
      return;
    }
    if (feedback.impactOccurred) feedback.impactOccurred(style === "medium" ? "medium" : "light");
  } catch (_err) {
    /* Ignore missing haptic support. */
  }
}

function telegramUserId() {
  const user = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
  return user && user.id ? String(user.id) : "anon";
}

function readStore() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    const data = raw ? JSON.parse(raw) : null;
    if (!data || data.uid !== telegramUserId()) return null;
    return data;
  } catch (_err) {
    return null;
  }
}

function writeStore() {
  try {
    localStorage.setItem(
      STORE_KEY,
      JSON.stringify({ uid: telegramUserId(), me: state.me, dash: state.dash }),
    );
  } catch (_err) {
    /* Private mode or quota: the in-memory copy still works. */
  }
}

/** Restore the last dashboard snapshot for an instant first paint. Returns true when a dashboard was cached. */
export function restoreSession() {
  const saved = readStore();
  if (!saved) return false;
  if (saved.me) {
    state.me = saved.me;
    applyLanguage(saved.me);
  }
  if (saved.dash) state.dash = saved.dash;
  return Boolean(state.dash);
}

function applyLanguage(me) {
  const code =
    (me && me.user && me.user.language) ||
    (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code) ||
    "uz";
  setLang(code);
}

async function rawFetch(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || "error");
    err.code = data.error;
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

/** Authenticated binary GET (receipt images): returns an object URL the caller must revoke. */
export async function apiBlob(path) {
  if (!state.token || Date.now() > state.tokenExp) await bootstrap();
  const res = await fetch(path, { headers: { Authorization: `Bearer ${state.token}` } });
  if (!res.ok) {
    const err = new Error("error");
    err.status = res.status;
    throw err;
  }
  const blob = await res.blob();
  return { url: URL.createObjectURL(blob), type: blob.type };
}

/** Authenticated call. A stale token is refreshed once, transparently. */
export async function api(path, options) {
  if (!state.token || Date.now() > state.tokenExp) await bootstrap();
  try {
    return await rawFetch(path, options);
  } catch (err) {
    if (err.status !== 401) throw err;
    state.token = "";
    await bootstrap();
    return rawFetch(path, options);
  }
}

/** One round trip: sign in with initData and receive the home dashboard. */
export function bootstrap() {
  if (signingIn) return signingIn;
  signingIn = (async () => {
    const initData = (tg && tg.initData) || "";
    const data = await rawFetch("/api/bootstrap", { method: "POST", body: JSON.stringify({ initData }) });
    state.token = data.token;
    state.tokenExp = Date.now() + Math.max(60, Number(data.expires_in || 0) - 60) * 1000;
    const { dash, ...me } = data;
    state.me = me;
    if (dash) {
      state.dash = dash;
      cache.set("/api/stats", { at: Date.now(), data: dash });
    }
    applyLanguage(me);
    writeStore();
    return data;
  })();
  signingIn
    .finally(() => {
      signingIn = null;
    })
    .catch(() => {});
  return signingIn;
}

export async function loadDash() {
  const dash = await load("/api/stats", { maxAge: 0 });
  state.dash = dash;
  writeStore();
  return dash;
}

/** Last good response for a GET path, or undefined. */
export function cached(path) {
  const hit = cache.get(path);
  return hit ? hit.data : undefined;
}

/** GET with an in-memory cache. Concurrent calls share one request. */
export function load(path, { maxAge = 15000 } = {}) {
  const hit = cache.get(path);
  if (hit && Date.now() - hit.at < maxAge) return Promise.resolve(hit.data);
  if (inflight.has(path)) return inflight.get(path);
  const job = api(path)
    .then((data) => {
      cache.set(path, { at: Date.now(), data });
      return data;
    })
    .finally(() => inflight.delete(path));
  inflight.set(path, job);
  return job;
}

export function remember(path, data) {
  cache.set(path, { at: Date.now(), data });
}

export function forget(prefix) {
  for (const key of [...cache.keys()]) {
    if (key.startsWith(prefix)) cache.delete(key);
  }
}

/** Warm the cache for screens the user is likely to open next. */
export function prefetch(paths) {
  const run = () => paths.forEach((path) => load(path).catch(() => {}));
  if ("requestIdleCallback" in window) window.requestIdleCallback(run, { timeout: 1500 });
  else setTimeout(run, 300);
}

export function go(hash) {
  const next = hash.startsWith("#") ? hash : `#/${hash}`;
  if (location.hash === next) {
    window.dispatchEvent(new Event("hashchange"));
    return;
  }
  location.hash = next;
}

export function parseRoute() {
  const raw = (location.hash || "#/home").replace(/^#\/?/, "");
  const parts = raw.split("/").filter(Boolean);
  const tab = parts[0] || "home";
  // "#/admin/pay/12": a named sub-view, then an optional numeric id.
  const named = parts[1] && !/^-?\d+$/.test(parts[1]);
  const sub = named ? parts[1] : null;
  const rawId = named ? parts[2] : parts[1];
  const id = rawId ? Number(rawId) : null;
  return { tab, sub, id: Number.isFinite(id) ? id : null };
}

export function firstChatId() {
  const chats = (state.dash && state.dash.chats) || [];
  return chats.length === 1 ? chats[0].id : null;
}

export function openTelegram(path) {
  const name = state.me && state.me.bot_username;
  if (!name) return;
  const url = `https://t.me/${name}${path || ""}`;
  if (tg && tg.openTelegramLink) tg.openTelegramLink(url);
  else window.open(url, "_blank");
}

/** Open any t.me link inside Telegram (falls back to a new tab in a browser). */
export function openLink(url) {
  if (!/^https:\/\/t\.me\//.test(url)) return;
  if (tg && tg.openTelegramLink) tg.openTelegramLink(url);
  else window.open(url, "_blank", "noopener");
}

/** Save the current session snapshot (after a local change such as the app language). */
export function persist() {
  writeStore();
}

/** Server-assigned roles (never decided on the client; the server re-checks every call). */
export function roles() {
  const fromDash = state.dash && state.dash.roles;
  const fromMe = state.me && state.me.roles;
  return fromDash || fromMe || null;
}

export function hasRole(name) {
  const list = roles();
  return Boolean(list && list.includes(name));
}

/** Owners, chat admins and super admins manage chats; others only see their results. */
export function isManager() {
  const list = roles();
  if (!list) return true; // unknown yet: keep the familiar owner layout until bootstrap answers
  return list.includes("owner") || list.includes("admin") || list.includes("super_admin");
}

export function memberData() {
  return (state.dash && state.dash.member) || null;
}

/** Chats the leaderboard picker may show: managed chats first, then member chats. */
export function boardChats() {
  const seen = new Set();
  const out = [];
  const managed = (state.dash && state.dash.chats) || [];
  const member = (memberData() && memberData().chats) || [];
  [...managed, ...member].forEach((chat) => {
    if (seen.has(chat.id)) return;
    seen.add(chat.id);
    out.push(chat);
  });
  return out;
}
