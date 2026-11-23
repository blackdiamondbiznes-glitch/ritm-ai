import { api, cached, forget, go, haptic, isManager, isStudent, isTutor, load, loadDash, openLink, persist, remember, state, tg } from "./api.js";
import { setLang } from "./i18n.js";
import {
  current,
  escapeHtml,
  formatNumber,
  labelNav,
  setBusy,
  setHtml,
  showError,
  skeleton,
  t,
  toast,
  withBusy,
} from "./ui.js";
import { onlyStudent, showsPlan } from "./home.js";
import { renderPlanPay } from "./pay.js";

const LANG_NAMES = { uz: "🇺🇿 O‘zbekcha", ru: "🇷🇺 Русский", en: "🇬🇧 English" };
const SETTINGS = "/api/me/settings";
const PAYMENTS = "/api/me/payments";
const CONNECT = "/api/connect";
const TERMS = "/api/docs/terms";
const FAQ_COUNT = 7;
const PRIVACY_COUNT = 6;

/** Paths worth warming once the dashboard is in. */
export function profileWarmPaths() {
  const paths = [SETTINGS];
  paths.push(CONNECT);
  if (isManager()) paths.push(PAYMENTS);
  return paths;
}

/* ---------- building blocks ---------- */

function row({ icon, color, title, sub = "", value = "", go: target = "", act = "", chevron = true }) {
  const attrs = target ? `data-go="${escapeHtml(target)}"` : act ? `data-act="${escapeHtml(act)}"` : "";
  return `<button type="button" class="lrow" ${attrs}>
    <span class="tile" style="--tile:${color}">${icon}</span>
    <span class="lrow-text"><span class="lrow-title">${escapeHtml(title)}</span>${sub ? `<span class="lrow-sub">${escapeHtml(sub)}</span>` : ""}</span>
    ${value ? `<span class="lrow-value">${escapeHtml(value)}</span>` : ""}
    ${chevron ? `<span class="chev" aria-hidden="true">›</span>` : ""}
  </button>`;
}

function group(title, rows) {
  const body = rows.filter(Boolean).join("");
  if (!body) return "";
  return `<section class="lgroup">${title ? `<div class="lgroup-title">${escapeHtml(title)}</div>` : ""}<div class="lgroup-body">${body}</div></section>`;
}

function hasBackButton() {
  return Boolean(tg && tg.BackButton && (!tg.isVersionAtLeast || tg.isVersionAtLeast("6.1")));
}

function subHead(title) {
  const back = hasBackButton() ? "" : `<button type="button" class="back-link" data-go="profile" aria-label="‹">‹</button>`;
  return `<div class="sub-head">${back}<h2 class="page-title">${escapeHtml(title)}</h2></div>`;
}

function bindRows(root = document) {
  root.querySelectorAll("[data-go]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(node.getAttribute("data-go"));
    });
  });
  root.querySelectorAll('[data-act="support"]').forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      const handle = state.me && state.me.support;
      if (handle) openLink(`https://t.me/${handle}`);
    });
  });
}

function langName(code) {
  return LANG_NAMES[String(code || "").slice(0, 2)] || code || "—";
}

function zoneOffset(zone) {
  try {
    const part = new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "shortOffset" })
      .formatToParts(new Date())
      .find((item) => item.type === "timeZoneName");
    return part ? part.value.replace("GMT", "UTC") : "";
  } catch (_err) {
    return "";
  }
}

function zoneName(zone) {
  return zone === "UTC" ? "UTC" : String(zone || "").split("/").pop().replace(/_/g, " ");
}

function founderValue(plan) {
  if (plan.founder_slots == null) return null;
  if (plan.founder_keep) return t("valYours");
  if (plan.founder_remaining > 0) return t("valSlots", { n: plan.founder_remaining });
  return t("valEnded");
}

/* ---------- main screen ---------- */

export function renderProfile() {
  const me = state.me || { user: {}, roles: [] };
  const user = me.user || {};
  const plan = (state.dash && state.dash.plan) || {};
  const chats = (state.dash && state.dash.chats) || [];
  const prefs = cached(SETTINGS);
  const name = user.name || user.username || t("user");
  const roles = ((state.dash && state.dash.roles) || me.roles || []).map(roleLabel);
  const manager = isManager();
  const offCount = prefs ? [prefs.notify_reports, prefs.notify_expiry].filter((on) => !on).length : 0;
  const notifyValue = prefs ? (offCount ? t("valSomeOff", { n: offCount }) : t("valOn")) : "";
  const zone = prefs ? prefs.default_timezone : "";
  const founder = founderValue(plan);
  const student = onlyStudent();
  const pills = [`<span class="pill pill-ok">● ${escapeHtml(t("tgLinked"))}</span>`]
    .concat(roles.map((role) => `<span class="pill">${escapeHtml(role)}</span>`))
    .join("");
  setHtml(`
    <div class="phead">
      <div class="ring">${avatar(user, name)}</div>
      <div class="phead-name">${escapeHtml(name)}</div>
      ${user.username ? `<div class="phead-user">@${escapeHtml(user.username)}</div>` : ""}
      <div class="phead-pills">${pills}</div>
    </div>
    ${group(t("secMain"), [
      manager ? row({ icon: "🔔", color: "#f59e0b", title: t("rowNotify"), value: notifyValue, go: "profile/notify" }) : "",
      row({ icon: "🌐", color: "#3b82f6", title: t("rowLang"), value: langName(user.language), go: "profile/lang" }),
      student ? "" : row({ icon: "🎓", color: "#14b8a6", title: t(isTutor() ? "navCabinet" : "cabEnable"), go: "cabinet" }),
      isStudent() ? row({ icon: "🎒", color: "#0ea5e9", title: t("studyNav"), go: "study" }) : "",
      manager ? row({ icon: "🕐", color: "#8b5cf6", title: t("rowTz"), sub: t("rowTzSub"), value: zone ? zoneName(zone) : "", go: "profile/tz" }) : "",
    ])}
    ${
      showsPlan()
        ? group(t("secSub"), [
            row({ icon: "💎", color: "#06b6d4", title: t("rowPlan"), value: plan.plan_name || "", go: "profile/plan" }),
            row({ icon: "💳", color: "#22c55e", title: t("rowPayments"), sub: t("rowPaymentsSub"), go: "profile/payments" }),
            founder ? row({ icon: "🎁", color: "#ec4899", title: t("rowFounder"), value: founder, go: "profile/founder" }) : "",
          ])
        : ""
    }
    ${
      group(t("secChats"), [
        manager ? row({ icon: "💬", color: "#0ea5e9", title: t("rowChats"), value: t("valCount", { n: chats.length }), go: "chats" }) : "",
        row({ icon: "➕", color: "#10b981", title: manager ? t("rowConnect") : t("ownCtaBtn"), sub: t("rowConnectSub"), go: "profile/connect" }),
      ])
    }
    ${group(t("secHelp"), [
      me.support ? row({ icon: "💬", color: "#6366f1", title: t("rowSupport"), value: `@${me.support}`, act: "support" }) : "",
      row({ icon: "❓", color: "#f97316", title: t("rowFaq"), go: "profile/faq" }),
    ])}
    ${group(t("secDocs"), [
      row({ icon: "📄", color: "#64748b", title: t("rowTerms"), go: "profile/terms" }),
      row({ icon: "🔒", color: "#475569", title: t("rowPrivacy"), go: "profile/privacy" }),
    ])}
    ${student ? `<button type="button" class="link-muted" data-go="cabinet">${escapeHtml(t("cabTeacherAsk"))}</button>` : ""}
    <p class="app-foot">${escapeHtml(t("appVersion"))}</p>
  `);
  bindAvatar(name);
  bindRows();
  if (!prefs && manager) {
    load(SETTINGS)
      .then(() => {
        const { tab, sub } = currentRoute();
        if (tab === "profile" && !sub) renderProfile();
      })
      .catch(() => {});
  }
}

function currentRoute() {
  const raw = (location.hash || "").replace(/^#\/?/, "").split("/");
  return { tab: raw[0] || "home", sub: raw[1] || null };
}

/* ---------- sub-screens ---------- */

const SUBS = {
  notify: renderNotify,
  lang: renderLang,
  tz: renderZone,
  plan: renderPlan,
  payments: renderPayments,
  founder: renderFounder,
  connect: renderConnect,
  faq: renderFaq,
  terms: renderTerms,
  privacy: renderPrivacy,
};

export function isProfileSub(sub) {
  return Object.prototype.hasOwnProperty.call(SUBS, sub);
}

export async function renderProfileSub(sub, seq) {
  const draw = SUBS[sub];
  if (!draw) {
    go("profile");
    return;
  }
  await draw(seq);
}

/** Cached-first GET: paint at once from the cache, refresh quietly, repaint if still on screen. */
async function withData(path, seq, paint, { kind = "list", maxAge = 0 } = {}) {
  const hit = cached(path);
  if (hit) paint(hit);
  else setHtml(skeleton(kind));
  setBusy(true);
  try {
    const data = await load(path, { maxAge });
    if (current(seq) && data !== hit) paint(data);
  } catch (err) {
    if (current(seq) && !hit) showError(err);
  } finally {
    if (current(seq)) setBusy(false);
  }
}

async function patchSettings(body) {
  const data = await api(SETTINGS, { method: "PATCH", body: JSON.stringify(body) });
  remember(SETTINGS, data);
  return data;
}

function renderNotify(seq) {
  return withData(SETTINGS, seq, (prefs) => {
    const sw = (id, on, title, hint, icon, color) => `<label class="lrow">
      <span class="tile" style="--tile:${color}">${icon}</span>
      <span class="lrow-text"><span class="lrow-title">${escapeHtml(title)}</span><span class="lrow-sub">${escapeHtml(hint)}</span></span>
      <input type="checkbox" class="switch" id="${id}"${on ? " checked" : ""} />
    </label>`;
    const info = (icon, title) => `<div class="lrow static"><span class="tile" style="--tile:#334155">${icon}</span>
      <span class="lrow-text"><span class="lrow-title">${escapeHtml(title)}</span></span><span class="lrow-value">✓</span></div>`;
    setHtml(`
      ${subHead(t("rowNotify"))}
      ${group("", [
        sw("notify_reports", prefs.notify_reports, t("ntReports"), t("ntReportsHint"), "📊", "#f59e0b"),
        sw("notify_expiry", prefs.notify_expiry, t("ntExpiry"), t("ntExpiryHint"), "⏳", "#ef4444"),
      ])}
      ${group(t("ntAlways"), [info("💳", t("ntAlwaysPay")), info("⚠️", t("ntAlwaysGone"))])}
      <p class="muted small-text pad-x">${escapeHtml(t("ntWhere"))}</p>
    `);
    bindRows();
    ["notify_reports", "notify_expiry"].forEach((key) => {
      const input = document.getElementById(key);
      input.addEventListener("change", async () => {
        input.disabled = true;
        try {
          haptic("light");
          await patchSettings({ [key]: input.checked });
          haptic("success");
          toast(t("saved"));
        } catch (_err) {
          input.checked = !input.checked;
          haptic("error");
          toast(t("error"), "err");
        } finally {
          input.disabled = false;
        }
      });
    });
  }, { maxAge: 15000 });
}

function choiceList(items, selected) {
  return items
    .map(
      ({ value, title, sub }) => `<button type="button" class="lrow choice${value === selected ? " on" : ""}" data-choice="${escapeHtml(value)}">
        <span class="lrow-text"><span class="lrow-title">${escapeHtml(title)}</span>${sub ? `<span class="lrow-sub">${escapeHtml(sub)}</span>` : ""}</span>
        <span class="tick" aria-hidden="true">${value === selected ? "✓" : ""}</span>
      </button>`,
    )
    .join("");
}

function bindChoices(save) {
  document.querySelectorAll("[data-choice]").forEach((node) => {
    node.addEventListener("click", () => {
      if (node.classList.contains("on")) return;
      withBusy(node, () => save(node.getAttribute("data-choice")));
    });
  });
}

function renderLang() {
  const user = (state.me && state.me.user) || {};
  const selected = String(user.language || "uz").slice(0, 2);
  const items = ["uz", "ru", "en"].map((code) => ({ value: code, title: langName(code) }));
  setHtml(`
    ${subHead(t("rowLang"))}
    ${group("", [choiceList(items, selected)])}
    <p class="muted small-text pad-x">${escapeHtml(t("langHint"))}</p>
  `);
  bindRows();
  bindChoices(async (code) => {
    try {
      haptic("light");
      await patchSettings({ language: code });
      if (state.me && state.me.user) state.me.user.language = code;
      setLang(code);
      document.documentElement.lang = code;
      persist();
      labelNav();
      haptic("success");
      renderLang();
      toast(t("saved"));
    } catch (_err) {
      haptic("error");
      toast(t("error"), "err");
    }
  });
}

function renderZone(seq) {
  return withData(SETTINGS, seq, (prefs) => {
    const items = (prefs.timezones || []).map((zone) => ({ value: zone, title: zoneName(zone), sub: `${zone} · ${zoneOffset(zone)}` }));
    setHtml(`
      ${subHead(t("rowTz"))}
      ${group("", [choiceList(items, prefs.default_timezone)])}
      <p class="muted small-text pad-x">${escapeHtml(t("tzHint"))}</p>
    `);
    bindRows();
    bindChoices(async (zone) => {
      try {
        await patchSettings({ default_timezone: zone });
        forget("/api/chats/");
        haptic("success");
        toast(t("saved"));
        if (current(seq)) renderZone(seq);
      } catch (_err) {
        haptic("error");
        toast(t("error"), "err");
      }
    });
  }, { maxAge: 15000 });
}

function renderPlan(seq) {
  return renderPlanPay(seq, { subHead, bindRows });
}

const UZ_MONTHS = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const lang = String((state.me && state.me.user && state.me.user.language) || "uz").slice(0, 2);
  // Browsers format uz-UZ inconsistently ("2026 M11 21"), so Uzbek dates are built by hand.
  if (lang === "uz") return `${date.getDate()}-${UZ_MONTHS[date.getMonth()]}, ${date.getFullYear()}`;
  return date.toLocaleDateString(lang === "ru" ? "ru-RU" : "en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function renderPayments(seq) {
  return withData(PAYMENTS, seq, (data) => {
    const rows = (data.payments || [])
      .map((pay) => {
        const tone = pay.status === "approved" ? "ok" : pay.status === "rejected" || pay.status === "expired" || pay.status === "canceled" ? "bad" : "wait";
        const facts = [pay.plan, pay.months ? t("payMonths", { n: pay.months }) : "", `${formatNumber(pay.amount_uzs)} so'm`, formatDate(pay.submitted_at || pay.created_at)]
          .filter(Boolean)
          .join(" · ");
        return `<div class="pay-item">
          <div class="row space"><strong class="mono">${escapeHtml(pay.ref || `#${pay.id}`)}</strong><span class="status-pill ${tone}">${escapeHtml(t(`pst_${pay.status}`))}</span></div>
          <div class="muted small-text">${escapeHtml(facts)}</div>
          ${pay.reason ? `<div class="pay-reason">${escapeHtml(t("payReason", { r: pay.reason }))}</div>` : ""}
        </div>`;
      })
      .join("");
    setHtml(`
      ${subHead(t("rowPayments"))}
      ${rows ? `<div class="lgroup-body pay-list">${rows}</div>` : `<div class="card muted">${escapeHtml(t("payEmpty"))}</div>`}
    `);
    bindRows();
  });
}

function renderFounder() {
  const plan = (state.dash && state.dash.plan) || {};
  const slots = plan.founder_slots || 0;
  const left = plan.founder_remaining || 0;
  const status = plan.founder_keep
    ? `<p class="ok">✅ ${escapeHtml(t("founderKeep"))}</p>`
    : left > 0
      ? `<p class="big">${escapeHtml(t("founderLeft", { left, slots }))}</p>`
      : `<p class="muted">${escapeHtml(t("founderGone"))}</p>`;
  const pct = slots ? Math.round(((slots - left) / slots) * 100) : 0;
  setHtml(`
    ${subHead(t("rowFounder"))}
    <div class="card">
      <div class="founder-badge">🎁 −30%</div>
      <p>${escapeHtml(t("founderAbout", { slots }))}</p>
      ${status}
      ${slots ? `<div class="meter"><i style="width:${pct}%"></i></div>` : ""}
      ${!plan.founder_keep && left > 0 ? `<button type="button" class="primary" id="pay">${escapeHtml(t("payInApp"))}</button>` : ""}
    </div>
  `);
  bindRows();
  const btn = document.getElementById("pay");
  if (btn) btn.onclick = () => go("profile/plan");
}

const CONNECT_ERRORS = {
  gone: "cnGone",
  bot_rights: "cnRights",
  not_admin: "cnNotAdmin",
  limit: "cnLimitFull",
  owned: "cnOwned",
  unavailable: "cnOffline",
};

function renderConnect(seq) {
  return withData(CONNECT, seq, (data) => paintConnect(data, seq));
}

function paintConnect(data, seq) {
  const links = data.links || {};
  const pending = data.pending || [];
  const limit =
    data.chats_limit != null
      ? `<p class="muted small-text">${escapeHtml(t("cnLimit", { used: data.chats_used, max: data.chats_limit }))}</p>`
      : "";
  const atLimit = data.chats_limit != null && Number(data.chats_used) >= Number(data.chats_limit);
  const full =
    data.can_confirm === false
      ? `<p class="err small-text pad-x">${escapeHtml(t("cnOffline"))}</p>`
      : atLimit
        ? `<p class="err small-text pad-x">${escapeHtml(t("cnLimitFull"))}</p>`
        : "";
  const items = pending
    .map(
      (item) => `<div class="lrow static pending-row" data-busy-group>
        <span class="tile" style="--tile:${item.type === "channel" ? "#0ea5e9" : "#10b981"}">${item.type === "channel" ? "📢" : "👥"}</span>
        <span class="lrow-text"><span class="lrow-title">${escapeHtml(item.title || String(item.telegram_chat_id))}</span></span>
        <button type="button" class="ghost small" data-decline="${item.telegram_chat_id}">${escapeHtml(t("cnDecline"))}</button>
        <button type="button" class="primary small" data-confirm="${item.telegram_chat_id}"${data.can_confirm === false ? " disabled" : ""}>${escapeHtml(t("cnConfirm"))}</button>
      </div>`,
    )
    .join("");
  setHtml(`
    ${subHead(t("rowConnect"))}
    <div class="card">
      <ol class="steps">
        <li>${escapeHtml(t("cnStep1"))}</li>
        <li>${escapeHtml(t("cnStep2"))}</li>
        <li>${escapeHtml(t("cnStep3"))}</li>
      </ol>
      <div class="cn-links">
        ${links.group ? `<button type="button" class="primary" data-link="${escapeHtml(links.group)}">👥 ${escapeHtml(t("cnGroup"))}</button>` : ""}
        ${links.channel ? `<button type="button" class="ghost" data-link="${escapeHtml(links.channel)}">📢 ${escapeHtml(t("cnChannel"))}</button>` : ""}
      </div>
      ${limit}
    </div>
    <div class="lgroup-title">${escapeHtml(t("cnPending"))}</div>
    ${items ? `<div class="lgroup-body">${items}</div>${full}` : `<div class="card muted">${escapeHtml(t("cnNone"))}</div>`}
    <div class="row quick">
      <button type="button" class="ghost" id="cnRefresh">🔄 ${escapeHtml(t("cnRefresh"))}</button>
      ${links.bot ? `<button type="button" class="ghost" data-link="${escapeHtml(links.bot)}">🤖 ${escapeHtml(t("cnInBot"))}</button>` : ""}
    </div>
  `);
  bindRows();
  document.querySelectorAll("[data-link]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      openLink(node.getAttribute("data-link"));
    });
  });
  const refresh = document.getElementById("cnRefresh");
  refresh.onclick = () =>
    withBusy(refresh, async () => {
      try {
        const before = isManager();
        const [fresh] = await Promise.all([load(CONNECT, { maxAge: 0 }), loadDash().catch(() => null)]);
        if (!current(seq)) return;
        if (!before && isManager() && !(fresh.pending || []).length) {
          haptic("success");
          toast(t("cnRoleUp"));
          go("chats");
          return;
        }
        paintConnect(fresh, seq);
      } catch (_err) {
        toast(t("error"), "err");
      }
    });
  document.querySelectorAll("[data-confirm]").forEach((node) => {
    node.addEventListener("click", () => withBusy(node, () => confirmChat(Number(node.getAttribute("data-confirm")), seq)));
  });
  document.querySelectorAll("[data-decline]").forEach((node) => {
    node.addEventListener("click", () =>
      withBusy(node, async () => {
        try {
          await api(`${CONNECT}/decline`, { method: "POST", body: JSON.stringify({ telegram_chat_id: Number(node.getAttribute("data-decline")) }) });
          const fresh = await load(CONNECT, { maxAge: 0 });
          if (current(seq)) paintConnect(fresh, seq);
        } catch (_err) {
          toast(t("error"), "err");
        }
      }),
    );
  });
}

async function confirmChat(telegramChatId, seq) {
  try {
    haptic("medium");
    const done = await api(CONNECT, { method: "POST", body: JSON.stringify({ telegram_chat_id: telegramChatId }) });
    forget(CONNECT);
    forget("/api/stats");
    haptic("success");
    toast(done.already ? t("cnAlready") : done.trial_started ? t("cnTrial", { n: done.trial_days }) : t("cnDone"));
    await loadDash().catch(() => {}); // roles change from member to owner
    if (current(seq)) go(done.already ? `chats/${done.chat_id}` : `chats/edit/${done.chat_id}`);
  } catch (err) {
    haptic("error");
    const key = CONNECT_ERRORS[err && err.code];
    const data = (err && err.data) || {};
    toast(key === "cnLimitFull" && data.max ? t("cnLimit", { used: data.used, max: data.max }) : t(key || "error"), "err");
    forget(CONNECT);
    if (err && err.code === "gone") {
      const fresh = await load(CONNECT, { maxAge: 0 }).catch(() => null);
      if (fresh && current(seq)) paintConnect(fresh, seq);
    }
  }
}

function renderFaq() {
  const items = Array.from({ length: FAQ_COUNT }, (_v, i) => i + 1)
    .map(
      (n) => `<details class="faq"><summary>${escapeHtml(t(`faqQ${n}`))}</summary><p>${escapeHtml(t(`faqA${n}`))}</p></details>`,
    )
    .join("");
  const support = state.me && state.me.support;
  setHtml(`
    ${subHead(t("rowFaq"))}
    <div class="lgroup-body faq-list">${items}</div>
    ${support ? group("", [row({ icon: "💬", color: "#6366f1", title: t("rowSupport"), value: `@${support}`, act: "support" })]) : ""}
  `);
  bindRows();
}

function renderTerms(seq) {
  return withData(TERMS, seq, (doc) => {
    setHtml(`
      ${subHead(t("rowTerms"))}
      <div class="card doc">
        <p class="muted small-text">${escapeHtml(t("docVersion", { v: doc.version }))}</p>
        <div class="doc-text">${escapeHtml(doc.text)}</div>
      </div>
    `);
    bindRows();
  }, { maxAge: 600000 });
}

function renderPrivacy() {
  const parts = Array.from({ length: PRIVACY_COUNT }, (_v, i) => i + 1)
    .map((n) => `<h3>${escapeHtml(t(`prvH${n}`))}</h3><p>${escapeHtml(t(`prvP${n}`))}</p>`)
    .join("");
  setHtml(`
    ${subHead(t("rowPrivacy"))}
    <div class="card doc">${parts}</div>
  `);
  bindRows();
}

/* ---------- shared helpers ---------- */

function bindAvatar(name) {
  const img = document.querySelector(".avatar img");
  if (img) {
    img.addEventListener("error", () => {
      const holder = img.parentElement;
      img.remove();
      holder.textContent = initials(name);
    });
  }
}

function roleLabel(role) {
  if (role === "super_admin") return t("roleAdmin");
  if (role === "owner") return t("roleOwner");
  if (role === "admin") return t("roleChatAdmin");
  if (role === "member") return t("roleMember");
  return role;
}

function photoUrl(user) {
  const direct = user && user.photo_url;
  const unsafe = tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.photo_url;
  const url = direct || unsafe || "";
  return /^https:\/\//.test(url) ? url : "";
}

function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((part) => Array.from(part)[0] || "").join("");
  return (letters || "?").toUpperCase();
}

function avatar(user, name) {
  const url = photoUrl(user);
  if (url) return `<div class="avatar"><img src="${escapeHtml(url)}" alt="" referrerpolicy="no-referrer" /></div>`;
  return `<div class="avatar">${escapeHtml(initials(name))}</div>`;
}
