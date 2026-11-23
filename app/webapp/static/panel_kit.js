import { t } from "./i18n.js";

/** Shared helpers for the teacher web panel pages: fetch, escaping, dates (Tashkent), UI bits. */
export { t };
export const TZ = "Asia/Tashkent";
export const state = { me: null };

const LIMIT_KEYS = {
  limit_groups: "limitGroups",
  limit_students: "limitStudents",
  limit_fees: "limitFees",
  quota: "limitQuota",
  export: "limitExport",
};
const ERROR_KEYS = {
  empty: "pdErrEmpty",
  long: "pdErrLong",
  time: "schTime",
  span: "schSpan",
  slot: "schSlot",
  missing: "schMissing",
  link: "lesLinkBad",
  when: "pdErrWhen",
  future: "attFuture",
  rate_limit: "pdErrSlow",
  origin: "pdErrSession",
  unauthorized: "pdErrSession",
  pd_group_need: "stuGroupNeed",
  amount: "pdErrAmount",
};
const PLAN_NAMES = { free: "Free", start: "Start", pro: "Pro", agency: "Ultra" };

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
}

export function icon(name) {
  return `<svg class="ic" aria-hidden="true" focusable="false"><use href="#i-${name}"></use></svg>`;
}

export function money(amount) {
  return `${String(Math.round(Number(amount) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, " ")} so‘m`;
}

/** JSON request with the panel cookie. Errors carry the API code, status and body. */
export async function api(path, options = {}) {
  const init = { credentials: "same-origin", headers: { Accept: "application/json" }, ...options };
  if (options.body !== undefined) init.headers["Content-Type"] = "application/json";
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || "error");
    err.code = res.status === 401 ? "unauthorized" : data.error || "error";
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export const send = (path, method, body) => api(path, { method, body: JSON.stringify(body ?? {}) });

export function errorText(err) {
  const code = err && err.code;
  if (LIMIT_KEYS[code]) {
    const data = err.data || {};
    return t(LIMIT_KEYS[code], { plan: PLAN_NAMES[data.plan] || data.plan || "", limit: data.limit ?? "" });
  }
  return t(ERROR_KEYS[code] || "error");
}

/* ---------- dates, always on the Tashkent wall clock ---------- */

export function todayIso() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
}

function atNoon(iso) {
  return new Date(`${iso}T12:00:00+05:00`);
}

export function addDays(iso, count) {
  const date = atNoon(iso);
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0, 10);
}

export function mondayOf(iso) {
  const day = atNoon(iso).getUTCDay();
  return addDays(iso, day === 0 ? -6 : 1 - day);
}

/** 1 = Monday … 7 = Sunday for a YYYY-MM-DD day. */
export function weekdayOf(iso) {
  const day = atNoon(iso).getUTCDay();
  return day === 0 ? 7 : day;
}

/** "YYYY-MM-DDTHH:MM" in Tashkent for an ISO instant. */
export function wall(iso) {
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const pick = (type) => parts.find((part) => part.type === type).value;
  return `${pick("year")}-${pick("month")}-${pick("day")}T${pick("hour")}:${pick("minute")}`;
}

export const dayOf = (iso) => wall(iso).slice(0, 10);
export const clock = (iso) => wall(iso).slice(11, 16);

export function span(row) {
  return row.ends_at ? `${clock(row.starts_at)}–${clock(row.ends_at)}` : clock(row.starts_at);
}

/** "23-noyabr" style day and month. */
export function dayMonth(iso) {
  const [, m, d] = iso.split("-").map(Number);
  return t("dateDM", { day: d, month: t(`monthLong${m}`) });
}

export function longDay(iso) {
  return `${t(`dayLong${weekdayOf(iso)}`)}, ${dayMonth(iso)}`;
}

export function monthLabel(month) {
  const [y, m] = month.split("-").map(Number);
  return `${t(`monthLong${m}`)} ${y}`;
}

/* ---------- small UI pieces ---------- */

export function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  return (parts.slice(0, 2).map((part) => Array.from(part)[0] || "").join("") || "?").toUpperCase();
}

/** Page header. On phones the menu button and avatar menu replace the sidebar. */
export function head(title, lead, actions = "") {
  const me = state.me;
  const name = me ? me.user.name : "";
  const both = me && me.both_roles
    ? `<p class="pn-pop-note">${esc(t("pnlBothShort"))}</p><a href="/?role=student#/study">${esc(t("pnlToStudent"))}</a>`
    : "";
  return `<header class="pn-head">
    <button type="button" class="pn-icon-btn pn-only-phone" data-act="drawer" aria-label="${esc(t("pnlMenu"))}" aria-controls="pn-side">${icon("menu")}</button>
    <div class="pn-head-text"><p class="pn-eyebrow">${esc(t("pnlEyebrow"))}</p><h1>${esc(title)}</h1>${lead ? `<p class="pn-lead">${esc(lead)}</p>` : ""}</div>
    <div class="pn-head-actions">${actions}
      <div class="pn-head-me pn-only-phone">
        <button type="button" class="pn-avatar pn-avatar-btn" data-act="menu" aria-haspopup="true" aria-expanded="false" aria-controls="pn-pop" aria-label="${esc(name)}">${esc(initials(name))}</button>
        <div class="pn-pop" id="pn-pop" hidden>${both}
          <form method="post" action="/panel/logout"><button type="submit" class="pn-pop-item">${esc(t("pnlLogout"))}</button></form>
        </div>
      </div>
    </div>
  </header>`;
}

export function button(label, attrs = "", tone = "ghost", iconName = "") {
  return `<button type="button" class="pn-btn pn-btn-${tone}" ${attrs}>${iconName ? icon(iconName) : ""}<span>${esc(label)}</span></button>`;
}

export function chips(items, current, attr) {
  return `<div class="pd-chips" role="group">${items
    .map(([value, label]) => {
      const on = String(value) === String(current);
      return `<button type="button" class="pd-chip${on ? " on" : ""}" ${attr}="${esc(value)}" aria-pressed="${on}">${esc(label)}</button>`;
    })
    .join("")}</div>`;
}

export function tag(tone, text) {
  return `<span class="pd-tag pd-tag-${tone}">${esc(text)}</span>`;
}

export function empty(text) {
  return `<p class="pn-muted pn-empty">${esc(text)}</p>`;
}

export function loading(main, title) {
  main.innerHTML = `${head(title, "")}<p class="pn-loading" role="status">${esc(t("loading"))}</p>`;
}

export function failed(main, title, err) {
  main.innerHTML = `${head(title, "")}<section class="pn-card"><p>${esc(errorText(err))}</p>
    <button type="button" class="pn-btn pn-btn-primary" data-act="reload">${esc(t("retry"))}</button></section>`;
}

export function toast(text, tone = "ok") {
  let node = document.getElementById("pd-toast");
  if (!node) {
    node = document.createElement("div");
    node.id = "pd-toast";
    node.className = "pd-toast";
    node.setAttribute("role", "status");
    node.setAttribute("aria-live", "polite");
    document.body.appendChild(node);
  }
  node.textContent = text;
  node.dataset.tone = tone;
  node.classList.add("show");
  clearTimeout(node.timer);
  node.timer = setTimeout(() => node.classList.remove("show"), 3200);
}

/** Disable the button while work runs; show the API error as a toast. */
export async function busy(node, work) {
  if (!node || node.disabled) return;
  node.disabled = true;
  node.setAttribute("aria-busy", "true");
  try {
    await work();
  } catch (err) {
    toast(errorText(err), "err");
  } finally {
    node.disabled = false;
    node.removeAttribute("aria-busy");
  }
}

const handlers = new Map();
const rooted = new WeakSet();

/** Forget the previous page's click handlers. The shell calls this on every route. */
export function resetHandlers() {
  handlers.clear();
}

/**
 * Run `handler(node, event)` for clicks on `[attr]` inside root. One delegated listener per
 * root; registering the same attr again replaces the handler, so repaints never stack them.
 */
export function on(root, attr, handler) {
  handlers.set(attr, handler);
  if (rooted.has(root)) return;
  rooted.add(root);
  root.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    for (const [name, run] of handlers) {
      const node = event.target.closest(`[${name}]`);
      if (node && root.contains(node)) {
        run(node, event);
        return;
      }
    }
  });
}

/**
 * Modal form. `submit(form)` runs on save; the dialog closes when it resolves.
 * Uses <dialog>, so focus is trapped and Escape closes it.
 */
export function dialog(title, fields, submit, saveLabel = t("save")) {
  const node = document.createElement("dialog");
  node.className = "pd-dialog";
  node.setAttribute("aria-labelledby", "pd-dialog-title");
  node.innerHTML = `<form class="pd-form" novalidate>
    <div class="pd-dialog-head"><h2 id="pd-dialog-title">${esc(title)}</h2>
      <button type="button" class="pn-icon-btn" data-close aria-label="${esc(t("pdClose"))}">${icon("close")}</button></div>
    <div class="pd-dialog-body">${fields}</div>
    <div class="pd-dialog-foot">
      <button type="button" class="pn-btn pn-btn-ghost" data-close>${esc(t("pdCancel"))}</button>
      <button type="submit" class="pn-btn pn-btn-primary">${esc(saveLabel)}</button>
    </div></form>`;
  document.body.appendChild(node);
  const form = node.querySelector("form");
  const close = () => {
    node.close();
    node.remove();
  };
  node.addEventListener("cancel", () => node.remove());
  node.querySelectorAll("[data-close]").forEach((item) => item.addEventListener("click", close));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const go = form.querySelector('[type="submit"]');
    busy(go, async () => {
      await submit(form);
      close();
    });
  });
  node.showModal();
  const first = form.querySelector("input, select, textarea");
  if (first) first.focus();
  return node;
}

export function field(label, control, hint = "") {
  return `<label class="pd-field"><span class="pd-label">${esc(label)}</span>${control}${hint ? `<small class="pd-hint">${esc(hint)}</small>` : ""}</label>`;
}

export function input(name, value = "", attrs = "") {
  return `<input class="pd-input" name="${esc(name)}" value="${esc(value)}" ${attrs}>`;
}

export function select(name, options, current, attrs = "") {
  const list = options
    .map(([value, label]) => `<option value="${esc(value)}"${String(value) === String(current ?? "") ? " selected" : ""}>${esc(label)}</option>`)
    .join("");
  return `<select class="pd-input" name="${esc(name)}" ${attrs}>${list}</select>`;
}

export function dayToggles(selected = []) {
  return `<div class="pd-days" role="group">${[1, 2, 3, 4, 5, 6, 7]
    .map((day) => `<label class="pd-day"><input type="checkbox" name="weekdays" value="${day}"${selected.includes(day) ? " checked" : ""}><span>${esc(t(`day${day}`))}</span></label>`)
    .join("")}</div>`;
}

export function daysText(days) {
  return (days || []).map((day) => t(`day${day}`)).join(", ");
}

export function groupLabel(group) {
  return `${group.name || group.group_name || ""}${group.level ? ` · ${group.level}` : ""}`;
}

export function inviteLink(code) {
  const bot = state.me && state.me.bot_username;
  return bot && code ? `https://t.me/${bot}?start=enroll_${code}` : "";
}

export function provider(url) {
  if (!url) return "";
  try {
    const host = new URL(url).hostname;
    if (host.includes("meet.google")) return "Meet";
    if (host.includes("zoom")) return "Zoom";
    if (host.includes("teams")) return "Teams";
  } catch {
    return t("pnlLink");
  }
  return t("pnlLink");
}
