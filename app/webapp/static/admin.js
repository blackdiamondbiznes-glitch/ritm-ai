import { api, apiBlob, cached, forget, go, haptic, hasRole, load, remember, roles, tg } from "./api.js";
import { barChart, bindCharts, chartCard, compact, lineChart, monthLabel, PALETTE, periodChips } from "./charts.js";
import { current, escapeHtml, formatNumber, setBusy, setHtml, showError, skeleton, t, toast, withBusy } from "./ui.js";

/* Super-admin panel. Every call is re-checked on the server (SUPER_ADMIN_IDS); this file only renders. */

const BASE = "/api/admin";
const SECTIONS = [
  ["", "📊", "admOverview"],
  ["stats", "📈", "admStats"],
  ["payments", "💳", "admPayments"],
  ["tenants", "👥", "admTenants"],
  ["chats", "💬", "admChats"],
  ["audit", "🧾", "admAudit"],
];
const FILTERS = [
  ["queue", "admFilterQueue"],
  ["disputes", "admFilterDisputes"],
  ["fake", "admFilterFake"],
  ["approved", "admFilterApproved"],
  ["rejected", "admFilterRejected"],
  ["all", "admFilterAll"],
];
const REASONS = ["admR1", "admR2", "admR3", "admR4"];
const view = { payFilter: "queue", tenantQ: "", chatQ: "", statDays: 30 };
let receiptUrl = "";

export function adminWarmPaths() {
  return [`${BASE}/overview`, `${BASE}/payments?status=queue`];
}

export async function renderAdmin(sub, id, seq) {
  const known = roles();
  if (known && !hasRole("super_admin")) {
    go("home");
    return;
  }
  releaseReceipt();
  if (sub === "tenant" && id) return show(`${BASE}/tenants/${id}`, (d) => paintTenant(d), seq, "chat");
  if (sub === "pay" && id) return show(`${BASE}/payments/${id}`, (d) => paintPayment(d), seq, "chat");
  if (sub === "payments") return show(payPath(), (d) => paintPayments(d), seq);
  if (sub === "tenants") return searchView("tenants", seq);
  if (sub === "chats") return searchView("chats", seq);
  if (sub === "stats") return show(statsPath(), (d) => paintStats(d), seq);
  if (sub === "audit") return show(`${BASE}/audit?limit=100`, (d) => paintAudit(d), seq);
  return show(`${BASE}/overview`, (d) => paintOverview(d), seq, "home");
}

/** Cached copy first (instant), then a fresh copy in the background. */
async function show(path, paint, seq, kind = "list") {
  const hit = cached(path);
  if (hit) paint(hit);
  else setHtml(skeleton(kind));
  setBusy(true);
  try {
    const data = await load(path, { maxAge: hit ? 0 : 10000 });
    if (current(seq)) paint(data);
  } catch (err) {
    if (current(seq) && !hit) showError(err);
  } finally {
    if (current(seq)) setBusy(false);
  }
}

function statsPath() {
  return `${BASE}/charts?days=${view.statDays}`;
}

function payPath() {
  return `${BASE}/payments?status=${view.payFilter}`;
}

function frame(active, body) {
  const tabs = SECTIONS.map(
    ([key, icon, label]) =>
      `<button type="button" class="chip-btn${key === active ? " selected" : ""}" data-adm-go="${key ? `admin/${key}` : "admin"}">${icon} ${escapeHtml(t(label))}</button>`,
  ).join("");
  setHtml(`
    <h2 class="page-title">🛡️ ${escapeHtml(t("admTitle"))}</h2>
    <div class="chips adm-tabs">${tabs}</div>
    ${body}
  `);
  bindGo();
}

function bindGo(root = document) {
  root.querySelectorAll("[data-adm-go]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(node.getAttribute("data-adm-go"));
    });
  });
}

function money(value) {
  return `${formatNumber(value || 0)} so‘m`;
}

function when(iso, withYear = false) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const pad = (n) => String(n).padStart(2, "0");
  const day = `${pad(date.getDate())}.${pad(date.getMonth() + 1)}${withYear ? `.${date.getFullYear()}` : ""}`;
  return `${day} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function who(user) {
  if (!user) return t("admSystem");
  const name = user.name || (user.username ? `@${user.username}` : String(user.telegram_id));
  return name;
}

function statusPill(status) {
  return `<span class="adm-status st-${escapeHtml(status)}">${escapeHtml(t(`st_${status}`))}</span>`;
}

function kpi(icon, value, label, extra = "") {
  return `<div class="kpi"><div class="kpi-icon">${icon}</div>
    <div class="kpi-value">${escapeHtml(value)}</div>
    <div class="kpi-label">${escapeHtml(label)}</div>${extra ? `<div class="kpi-label">${escapeHtml(extra)}</div>` : ""}</div>`;
}

/* ---------- Overview ---------- */

function paintOverview(d) {
  const plans = (d.active_by_plan || [])
    .map((row) => `<div class="row space adm-line"><span>${escapeHtml(row.name)}</span><b>${escapeHtml(formatNumber(row.count))}</b></div>`)
    .join("");
  const queue = Number(d.payments_pending || 0) + Number(d.payments_disputed || 0);
  frame(
    "",
    `
    ${queue ? `<button type="button" class="card adm-alert list-btn" data-adm-go="admin/payments">💳 ${escapeHtml(t("admKpiPending"))}: <b>${queue}</b> →</button>` : ""}
    <div class="kpis adm-kpis">
      ${kpi("👥", formatNumber(d.tenants), t("admKpiTenants"))}
      ${kpi("⭐", formatNumber(d.active_total), t("admKpiActive"))}
      ${kpi("🧪", formatNumber(d.trials), t("admKpiTrials"))}
      ${kpi("💰", money(d.revenue_month_uzs), t("admKpiRevenue"), d.month)}
      ${kpi("📈", money(d.mrr_uzs), t("admKpiMrr"))}
      ${kpi("🏅", `${d.founder_used}/${d.founder_slots}`, t("admKpiFounder"), t("admFounderLeft", { u: d.founder_used, l: d.founder_left }))}
      ${kpi("⏳", formatNumber(d.payments_pending), t("admKpiPending"))}
      ${kpi("⚖️", formatNumber(d.payments_disputed), t("admKpiDisputed"))}
      ${kpi("⛔", formatNumber(d.payments_blocked_users), t("admKpiBlocked"))}
      ${kpi("⚠️", formatNumber(d.jobs_failed_24h), t("admKpiJobs"), `${t("admKpiRetry")}: ${d.jobs_retrying || 0}`)}
      ${kpi("🤖", formatNumber(d.ai_used_month), t("admKpiAi"), t("admKpiAiOwners", { n: d.ai_owners_month || 0 }))}
      ${kpi("💬", formatNumber(d.chats_active), t("admKpiChats"), `${t("admKpiUsers")}: ${formatNumber(d.users)}`)}
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("admByPlan"))}</div>
      ${plans || `<p class="muted">${escapeHtml(t("admEmpty"))}</p>`}
    </div>
  `,
  );
}

/* ---------- Payments ---------- */

function paymentRow(p) {
  const flags = [];
  if (p.duplicate_of) flags.push("♻️");
  if (p.is_fake) flags.push("🚩");
  if (p.disputed_at) flags.push("⚖️");
  return `<button type="button" class="list-btn adm-row" data-adm-go="admin/pay/${p.id}">
    <div class="row space"><b>${escapeHtml(p.ref || `#${p.id}`)} ${flags.join("")}</b>${statusPill(p.status)}</div>
    <div class="row space"><span>${escapeHtml(who(p.owner))}</span><b>${escapeHtml(money(p.amount_uzs))}</b></div>
    <div class="adm-meta">${escapeHtml(p.plan_name || "")} · ${p.months || 1} oy · ${escapeHtml(when(p.submitted_at || p.created_at))}${p.card_last4 ? ` · *${escapeHtml(p.card_last4)}` : ""}</div>
  </button>`;
}

function paintPayments(d) {
  const chips = FILTERS.map(
    ([key, label]) =>
      `<button type="button" class="chip-btn${key === view.payFilter ? " selected" : ""}" data-filter="${key}">${escapeHtml(t(label))}</button>`,
  ).join("");
  const rows = (d.payments || []).map(paymentRow).join("");
  frame(
    "payments",
    `
    <div class="chips adm-filters">${chips}</div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("admPaymentsOf", { n: (d.payments || []).length }))}</div>
      ${rows || `<p class="muted">${escapeHtml(t("admEmpty"))}</p>`}
    </div>
  `,
  );
  document.querySelectorAll("[data-filter]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      view.payFilter = node.getAttribute("data-filter");
      go("admin/payments");
    });
  });
}

function fact(label, value) {
  return `<div class="row space adm-line"><span class="muted">${escapeHtml(label)}</span><span>${value}</span></div>`;
}

function label(prefix, key) {
  const text = t(`${prefix}${key}`);
  return text === `${prefix}${key}` ? key : text;
}

function eventRow(e, withLink = true) {
  const from = e.from_status ? label("st_", e.from_status) : "—";
  const to = e.to_status ? label("st_", e.to_status) : "—";
  const change = e.from_status !== e.to_status && (e.from_status || e.to_status) ? ` · ${escapeHtml(from)} → ${escapeHtml(to)}` : "";
  const data = e.data || {};
  const note = data.reason || data.note || data.text || "";
  const via = data.via ? ` · ${escapeHtml(data.via)}` : "";
  const ref = withLink && e.payment_id ? `<span class="link-btn" data-adm-go="admin/pay/${e.payment_id}">#${e.payment_id}</span> · ` : "";
  return `<div class="hist-row"><div class="hist-body">
    <div class="hist-q">${escapeHtml(label("ev_", e.action))}${change}</div>
    ${note ? `<div class="hist-a">${escapeHtml(note)}</div>` : ""}
    <div class="hist-meta">${ref}${escapeHtml(who(e.actor))}${via} · ${escapeHtml(when(e.created_at, true))}</div>
  </div></div>`;
}

function paintPayment(p) {
  const flags = p.owner_flags || {};
  const open = p.status === "pending" || p.status === "disputed";
  const dups = (p.duplicates || [])
    .map((d) => `<button type="button" class="chip-btn" data-adm-go="admin/pay/${d.id}">${escapeHtml(d.ref || `#${d.id}`)} · ${escapeHtml(t(`st_${d.status}`))}</button>`)
    .join("");
  const warn = [
    dups ? `<div class="adm-warn">${escapeHtml(t("admDupWarn"))}<div class="chips">${dups}</div></div>` : "",
    flags.fake_receipts ? `<div class="adm-warn">${escapeHtml(t("admFakeWarn", { n: flags.fake_receipts }))}</div>` : "",
    flags.payments_blocked ? `<div class="adm-warn">⛔ ${escapeHtml(t("admBlockedPay"))}</div>` : "",
  ].join("");
  const ownerLink = p.owner
    ? `<button type="button" class="link-btn" data-adm-go="admin/tenant/${p.owner.id}">${escapeHtml(who(p.owner))}${p.owner.username ? ` · @${escapeHtml(p.owner.username)}` : ""} →</button>`
    : "—";
  const actions = open
    ? `<div class="adm-actions" data-busy-group>
        <button type="button" class="primary" id="adm-approve">${escapeHtml(t("admApprove"))}</button>
        <button type="button" class="ghost" id="adm-reject">${escapeHtml(t("admReject"))}</button>
        <button type="button" class="danger" id="adm-fake">${escapeHtml(t("admMarkFake"))}</button>
      </div>
      <div id="adm-form"></div>`
    : p.status === "rejected" && !p.is_fake
      ? `<div class="adm-actions" data-busy-group><button type="button" class="danger" id="adm-fake">${escapeHtml(t("admMarkFake"))}</button></div><div id="adm-form"></div>`
      : "";
  setHtml(`
    <button type="button" class="link-btn adm-back" data-adm-go="admin/payments">${escapeHtml(t("admBack"))}</button>
    <h2 class="page-title">💳 ${escapeHtml(p.ref || `#${p.id}`)} ${statusPill(p.status)}</h2>
    ${warn}
    <div class="card">
      ${fact(t("admAmount"), `<b>${escapeHtml(money(p.amount_uzs))}</b>`)}
      ${p.base_amount_uzs ? fact(t("admBase"), escapeHtml(money(p.base_amount_uzs))) : ""}
      ${fact(t("plan"), `${escapeHtml(p.plan_name || "—")} · ${p.months || 1} oy`)}
      ${fact(t("admOwner"), ownerLink)}
      ${fact(t("admCard4"), p.card_last4 ? `*${escapeHtml(p.card_last4)}` : "—")}
      ${fact(t("admTransfer"), escapeHtml(when(p.transfer_at, true)))}
      ${fact(t("admSubmitted"), escapeHtml(when(p.submitted_at, true)))}
      ${fact(t("admTerms"), p.terms_version ? `${escapeHtml(p.terms_version)} · ${escapeHtml(when(p.terms_accepted_at, true))}` : "—")}
      ${p.reject_reason ? fact(t("admRejectReason"), escapeHtml(p.reject_reason === "fake_receipt" ? t("admFakeReason") : p.reject_reason)) : ""}
    </div>
    ${p.dispute_text ? `<div class="card"><div class="card-title">⚖️ ${escapeHtml(t("admDisputeText"))}</div><p>${escapeHtml(p.dispute_text)}</p><div class="adm-meta">${escapeHtml(when(p.disputed_at, true))}</div></div>` : ""}
    <div class="card">
      <div class="card-title">🧾 ${escapeHtml(t("admReceipt"))}</div>
      <div id="adm-receipt" class="adm-receipt">${p.has_receipt ? '<div class="sk" style="height:220px"></div>' : `<p class="muted">${escapeHtml(t("admNoReceipt"))}</p>`}</div>
    </div>
    ${actions}
    <div class="card">
      <div class="card-title">${escapeHtml(t("admEvents"))}</div>
      ${(p.events || []).map((e) => eventRow(e, false)).join("") || `<p class="muted">${escapeHtml(t("admEmpty"))}</p>`}
    </div>
  `);
  bindGo();
  if (p.has_receipt) showReceipt(p);
  bindPaymentActions(p);
}

function releaseReceipt() {
  if (receiptUrl) URL.revokeObjectURL(receiptUrl);
  receiptUrl = "";
}

async function showReceipt(p) {
  const box = document.getElementById("adm-receipt");
  try {
    const blob = await apiBlob(`${BASE}/payments/${p.id}/receipt`);
    if (!box.isConnected) {
      URL.revokeObjectURL(blob.url);
      return;
    }
    releaseReceipt();
    receiptUrl = blob.url;
    if (blob.type.startsWith("image/")) {
      box.innerHTML = `<a href="${blob.url}" target="_blank" rel="noopener"><img src="${blob.url}" alt="" /></a>`;
    } else {
      box.innerHTML = `<a class="ghost adm-pdf" href="${blob.url}" target="_blank" rel="noopener">📄 ${escapeHtml(t("admReceiptPdf"))}</a>`;
    }
  } catch (_err) {
    if (box.isConnected) box.innerHTML = `<p class="muted">${escapeHtml(t("admReceiptFail"))}</p>`;
  }
}

function ask(text) {
  return new Promise((resolve) => {
    if (tg && tg.showConfirm) {
      try {
        tg.showConfirm(text, (ok) => resolve(Boolean(ok)));
        return;
      } catch (_err) {
        /* Older clients: fall through to the browser dialog. */
      }
    }
    resolve(window.confirm(text));
  });
}

async function decide(p, action, body) {
  try {
    const data = await api(`${BASE}/payments/${p.id}/${action}`, { method: "POST", body: JSON.stringify(body || {}) });
    haptic("success");
    toast(t("admDone"));
    forget(`${BASE}/`);
    remember(`${BASE}/payments/${p.id}`, data);
    paintPayment(data);
  } catch (err) {
    haptic("error");
    const key = err.code === "status" ? "admErrStatus" : err.code === "reason" ? "admReasonNeed" : "error";
    toast(t(key), "err");
    if (err.code === "status") {
      forget(`${BASE}/`);
      go(`admin/pay/${p.id}`);
    }
  }
}

function bindPaymentActions(p) {
  const approve = document.getElementById("adm-approve");
  if (approve) {
    approve.onclick = async () => {
      if (!(await ask(t("admApproveAsk", { ref: p.ref || `#${p.id}`, amount: formatNumber(p.amount_uzs) })))) return;
      await withBusy(approve, () => decide(p, "approve"));
    };
  }
  const reject = document.getElementById("adm-reject");
  if (reject) reject.onclick = () => reasonForm(p);
  const fake = document.getElementById("adm-fake");
  if (fake) fake.onclick = () => fakeForm(p);
}

function reasonForm(p) {
  const box = document.getElementById("adm-form");
  const chips = REASONS.map((key) => `<button type="button" class="chip-btn" data-reason="${escapeHtml(t(key))}">${escapeHtml(t(key))}</button>`).join("");
  box.innerHTML = `<div class="card">
    <div class="card-title">${escapeHtml(t("admRejectReason"))}</div>
    <div class="chips">${chips}</div>
    <textarea id="adm-reason" rows="3" maxlength="500" placeholder="${escapeHtml(t("admReason"))}"></textarea>
    <button type="button" class="ghost" id="adm-reject-send" disabled>${escapeHtml(t("admRejectSend"))}</button>
  </div>`;
  const input = document.getElementById("adm-reason");
  const send = document.getElementById("adm-reject-send");
  const sync = () => {
    send.disabled = !input.value.trim();
  };
  input.addEventListener("input", sync);
  box.querySelectorAll("[data-reason]").forEach((chip) => {
    chip.addEventListener("click", () => {
      haptic("light");
      input.value = chip.getAttribute("data-reason");
      sync();
    });
  });
  send.onclick = () => withBusy(send, () => decide(p, "reject", { reason: input.value.trim() }));
  input.focus();
}

function fakeForm(p) {
  const box = document.getElementById("adm-form");
  box.innerHTML = `<div class="card">
    <p>${escapeHtml(t("admFakeAsk"))}</p>
    <textarea id="adm-note" rows="2" maxlength="500" placeholder="${escapeHtml(t("admFakeNote"))}"></textarea>
    <button type="button" class="danger" id="adm-fake-send">${escapeHtml(t("admMarkFake"))}</button>
  </div>`;
  const send = document.getElementById("adm-fake-send");
  send.onclick = () => withBusy(send, () => decide(p, "fake", { note: document.getElementById("adm-note").value.trim() }));
}

/* ---------- Tenants and chats (search) ---------- */

function searchView(kind, seq) {
  const key = kind === "tenants" ? "tenantQ" : "chatQ";
  frame(
    kind,
    `<input type="search" id="adm-q" class="adm-search" placeholder="${escapeHtml(t("admSearch"))}" value="${escapeHtml(view[key])}" />
     <div class="card" id="adm-list"></div>`,
  );
  const input = document.getElementById("adm-q");
  let timer = 0;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      view[key] = input.value.trim();
      fillList(kind, seq);
    }, 300);
  });
  return fillList(kind, seq);
}

async function fillList(kind, seq) {
  const q = kind === "tenants" ? view.tenantQ : view.chatQ;
  const path = `${BASE}/${kind}?q=${encodeURIComponent(q)}`;
  const paint = (data) => {
    const box = document.getElementById("adm-list");
    if (!box) return;
    const rows = kind === "tenants" ? (data.tenants || []).map(tenantRow) : (data.chats || []).map(chatRow);
    box.innerHTML = rows.join("") || `<p class="muted">${escapeHtml(t("admEmpty"))}</p>`;
    bindGo(box);
  };
  const hit = cached(path);
  if (hit) paint(hit);
  else {
    const box = document.getElementById("adm-list");
    if (box) box.innerHTML = '<div class="sk" style="height:18px"></div>'.repeat(5);
  }
  setBusy(true);
  try {
    const data = await load(path, { maxAge: hit ? 0 : 10000 });
    if (current(seq)) paint(data);
  } catch (err) {
    if (current(seq) && !hit) showError(err);
  } finally {
    if (current(seq)) setBusy(false);
  }
}

function tenantRow(u) {
  const tags = [];
  if (u.is_founder) tags.push(`<span class="chat-plan">${escapeHtml(t("admFounder"))}</span>`);
  if (u.payments_blocked) tags.push(`<span class="adm-status st-rejected">⛔</span>`);
  if (u.fake_receipts) tags.push(`<span class="adm-status st-disputed">🚩${u.fake_receipts}</span>`);
  return `<button type="button" class="list-btn adm-row" data-adm-go="admin/tenant/${u.id}">
    <div class="row space"><b>${escapeHtml(who(u))}</b><span class="chat-tags">${tags.join("")}<span class="chat-plan">${escapeHtml(u.plan_name)}</span></span></div>
    <div class="adm-meta">${u.username ? `@${escapeHtml(u.username)} · ` : ""}ID ${escapeHtml(u.telegram_id)} · ${escapeHtml(t("admChatsN", { n: u.chats }))}${u.expires_at ? ` · ${escapeHtml(t("admExpires", { d: when(u.expires_at, true) }))}` : ""}</div>
  </button>`;
}

function chatRow(c) {
  const sub = c.plan_name ? `<span class="chat-plan">${escapeHtml(c.plan_name)}</span>` : "";
  const owner = c.owner
    ? `<span class="link-btn" data-adm-go="admin/tenant/${c.owner.id}">${escapeHtml(who(c.owner))}</span>`
    : "—";
  return `<div class="adm-row">
    <div class="row space"><b>${escapeHtml(c.title || "Chat")}</b>${sub}</div>
    <div class="adm-meta">${c.username ? `@${escapeHtml(c.username)} · ` : ""}${escapeHtml(c.type)} · ${escapeHtml(c.is_active ? t("admActive") : t("admRemoved"))}${c.member_count != null ? ` · ${escapeHtml(t("members", { n: c.member_count }))}` : ""}</div>
    <div class="adm-meta">${escapeHtml(t("admOwner"))}: ${owner}${c.expires_at ? ` · ${escapeHtml(t("admExpires", { d: when(c.expires_at, true) }))}` : ""}</div>
  </div>`;
}

/* ---------- Tenant detail ---------- */

function paintTenant(d) {
  const u = d.user || {};
  const plan = d.plan || {};
  const chats = (d.chats || []).map(chatRow).join("");
  const pays = (d.payments || []).map(paymentRow).join("");
  const subs = (d.subscriptions || [])
    .map(
      (s) => `<div class="row space adm-line"><span>${escapeHtml(s.plan_name)} · ${escapeHtml(s.source)}</span><span>${statusText(s.status)} · ${escapeHtml(when(s.expires_at, true))}</span></div>`,
    )
    .join("");
  const audit = (d.audit || []).map(eventRow).join("");
  const options = (d.plans || [])
    .filter((p) => p.code !== "free")
    .map((p) => `<option value="${escapeHtml(p.code)}"${p.code === plan.code ? " selected" : ""}>${escapeHtml(p.name)}</option>`)
    .join("");
  const ai = plan.ai_limit != null ? t("admAiUsage", { u: formatNumber(plan.ai_used), l: formatNumber(plan.ai_limit) }) : "";
  setHtml(`
    <button type="button" class="link-btn adm-back" data-adm-go="admin/tenants">${escapeHtml(t("admBack"))}</button>
    <h2 class="page-title">👤 ${escapeHtml(who(u))}</h2>
    <p class="muted page-sub">${u.username ? `@${escapeHtml(u.username)} · ` : ""}ID ${escapeHtml(u.telegram_id)}${u.is_founder ? ` · ${escapeHtml(t("admFounder"))}` : ""}</p>
    ${u.payments_blocked ? `<div class="adm-warn">⛔ ${escapeHtml(t("admBlockedPay"))}</div>` : ""}
    ${u.fake_receipts ? `<div class="adm-warn">${escapeHtml(t("admFakeN", { n: u.fake_receipts }))}</div>` : ""}
    <div class="card">
      <div class="card-title">${escapeHtml(t("plan"))}</div>
      <div class="big">${escapeHtml(plan.name || "Free")}</div>
      <p>${plan.status ? statusText(plan.status) : ""}${plan.expires_at ? ` · ${escapeHtml(t("admExpires", { d: when(plan.expires_at, true) }))}` : ""}</p>
      ${ai ? `<p class="ai-left">${escapeHtml(ai)}</p>` : ""}
    </div>
    <div class="card" data-busy-group>
      <div class="card-title">🎁 ${escapeHtml(t("admGrant"))} / ${escapeHtml(t("admExtend"))}</div>
      <div class="adm-form-row">
        <select id="adm-plan">${options}</select>
        <input type="number" id="adm-days" min="1" max="3650" value="30" inputmode="numeric" aria-label="${escapeHtml(t("admDays"))}" />
      </div>
      <textarea id="adm-why" rows="2" maxlength="300" placeholder="${escapeHtml(t("admReason"))}"></textarea>
      <div class="adm-actions">
        <button type="button" class="primary" id="adm-grant">${escapeHtml(t("admGrant"))}</button>
        <button type="button" class="ghost" id="adm-extend">${escapeHtml(t("admExtend"))}</button>
        <button type="button" class="${u.payments_blocked ? "ghost" : "danger"}" id="adm-block">${escapeHtml(t(u.payments_blocked ? "admUnblock" : "admBlock"))}</button>
      </div>
    </div>
    <div class="card"><div class="card-title">💬 ${escapeHtml(t("admChats"))}</div>${chats || `<p class="muted">${escapeHtml(t("admEmpty"))}</p>`}</div>
    <div class="card"><div class="card-title">💳 ${escapeHtml(t("admPayHistory"))}</div>${pays || `<p class="muted">${escapeHtml(t("admEmpty"))}</p>`}</div>
    <div class="card"><div class="card-title">⭐ ${escapeHtml(t("admSubs"))}</div>${subs || `<p class="muted">${escapeHtml(t("admEmpty"))}</p>`}</div>
    <div class="card"><div class="card-title">🧾 ${escapeHtml(t("admAuditTrail"))}</div>${audit || `<p class="muted">${escapeHtml(t("admEmpty"))}</p>`}</div>
  `);
  bindGo();
  const reason = () => document.getElementById("adm-why").value.trim();
  const days = () => Number(document.getElementById("adm-days").value || 0);
  const post = (button, action, body) =>
    withBusy(button, async () => {
      if (!body.reason) {
        toast(t("admReasonNeed"), "err");
        document.getElementById("adm-why").focus();
        return;
      }
      try {
        const data = await api(`${BASE}/tenants/${u.id}/${action}`, { method: "POST", body: JSON.stringify(body) });
        haptic("success");
        toast(t("admDone"));
        forget(`${BASE}/`);
        remember(`${BASE}/tenants/${u.id}`, data);
        paintTenant(data);
      } catch (err) {
        haptic("error");
        const known = err.code && t(`admErr_${err.code}`) !== `admErr_${err.code}`;
        toast(err.code === "reason" ? t("admReasonNeed") : known ? t(`admErr_${err.code}`) : t("error"), "err");
      }
    });
  const grant = document.getElementById("adm-grant");
  grant.onclick = () => post(grant, "grant", { plan: document.getElementById("adm-plan").value, days: days(), reason: reason() });
  const extend = document.getElementById("adm-extend");
  extend.onclick = () => post(extend, "extend", { days: days(), reason: reason() });
  const block = document.getElementById("adm-block");
  block.onclick = () => post(block, "payments-block", { blocked: !u.payments_blocked, reason: reason() });
}

function statusText(status) {
  return escapeHtml(label("st_", status));
}

/* ---------- Audit and disputes ---------- */

function paintAudit(d) {
  const disputes = (d.disputes || []).map(paymentRow).join("");
  const rows = (d.audit || []).map(eventRow).join("");
  frame(
    "audit",
    `
    <div class="card"><div class="card-title">⚖️ ${escapeHtml(t("admDisputesTitle"))}</div>${disputes || `<p class="muted">${escapeHtml(t("admEmpty"))}</p>`}</div>
    <div class="card"><div class="card-title">🧾 ${escapeHtml(t("admAuditTitle"))}</div>${rows || `<p class="muted">${escapeHtml(t("admEmpty"))}</p>`}</div>
  `,
  );
}

/* ---------- Statistics (charts) ---------- */

function paintStats(d) {
  const months = d.months || [];
  const labels = months.map((m) => m.month);
  const mTitle = (i) => monthLabel(labels[i], true);
  const mTick = (key) => monthLabel(key);
  const col = (key) => months.map((m) => Number(m[key]) || 0);
  const total = (key) => col(key).reduce((a, b) => a + b, 0);
  const monthly = (opts) => barChart({ tick: mTick, title: mTitle, labels, ...opts });
  const daily = d.daily || [];
  const dLabels = daily.map((r) => r.date);
  const founder = d.founder || { slots: 0, used: 0, left: 0 };
  const share = founder.slots ? Math.min(100, (100 * founder.used) / founder.slots) : 0;
  const plans = (d.plans || []).map((p, i) => ({
    name: p.name,
    color: p.code === "trial" ? "#94a3b8" : PALETTE[i % PALETTE.length],
    values: months.map((m) => Number((m.active || {})[p.code]) || 0),
  }));
  const usedPlans = plans.filter((p) => p.values.some((v) => v > 0));
  if (usedPlans.length) plans.splice(0, plans.length, ...usedPlans);
  const last = months[months.length - 1] || {};
  plans.forEach((p) => (p.total = formatNumber(p.values[p.values.length - 1] || 0)));
  const moneyFmt = (v, full) => (full ? money(v) : compact(v));
  const failed = daily.reduce((a, r) => a + (Number(r.jobs_failed) || 0), 0);
  const done = daily.reduce((a, r) => a + (Number(r.jobs_done) || 0), 0);
  const aiDays = daily.reduce((a, r) => a + (Number(r.ai) || 0), 0);
  frame(
    "stats",
    `
    <p class="muted page-sub">${escapeHtml(t("admChMonths"))} · ${escapeHtml(d.timezone || "")}</p>
    ${chartCard(
      `💰 ${t("admChRevenue")}`,
      monthly({
        label: t("admChRevenue"),
        fmt: moneyFmt,
        series: [{ name: t("admChRevenue"), color: PALETTE[3], values: col("revenue_uzs"), total: money(total("revenue_uzs")) }],
      }) + `<p class="muted chart-note">${escapeHtml(t("admChPayments", { n: total("payments") }))} · ${escapeHtml(monthLabel(last.month || "", true))}: <b>${escapeHtml(money(last.revenue_uzs))}</b></p>`,
    )}
    ${chartCard(
      `🆕 ${t("admChNew")}`,
      monthly({
        label: t("admChNew"),
        series: [
          { name: t("admChTrials"), color: "#94a3b8", values: col("new_trials"), total: total("new_trials") },
          { name: t("admChPaid"), color: PALETTE[0], values: col("new_paid"), total: total("new_paid") },
          { name: t("admChGrants"), color: PALETTE[1], values: col("new_grants"), total: total("new_grants") },
        ],
      }),
    )}
    ${chartCard(
      `📉 ${t("admChChurn")}`,
      monthly({
        label: t("admChChurn"),
        series: [
          { name: t("admChChurnTrial"), color: "#94a3b8", values: col("churn_trial"), total: total("churn_trial") },
          { name: t("admChChurnPaid"), color: "var(--danger)", values: col("churn_paid"), total: total("churn_paid") },
        ],
      }),
    )}
    ${chartCard(`⭐ ${t("admChActive")}`, monthly({ label: t("admChActive"), series: plans }))}
    ${chartCard(
      `🏅 ${t("admChFounder")}`,
      `<div class="founder-meter" role="img" aria-label="${escapeHtml(`${founder.used}/${founder.slots}`)}"><i style="width:${share.toFixed(1)}%"></i></div>
      <p class="chart-note">${escapeHtml(t("admChFounderUsed", { u: founder.used, s: founder.slots, l: founder.left }))}</p>` +
        lineChart({
          label: t("admChFounder"),
          labels,
          tick: mTick,
          title: mTitle,
          series: [{ name: t("admChFounder"), color: "#f59e0b", values: col("founders"), area: true, total: founder.used }],
          legend: false,
        }),
    )}
    ${chartCard(
      `🤖 ${t("admChAiMonth")}`,
      monthly({ label: t("admChAiMonth"), series: [{ name: t("admChAi"), color: PALETTE[1], values: col("ai"), total: formatNumber(total("ai")) }] }),
    )}
    ${periodChips(d.days || view.statDays)}
    ${chartCard(
      `🤖 ${t("admChAiDay")}`,
      barChart({ label: t("admChAiDay"), labels: dLabels, series: [{ name: t("admChAi"), color: PALETTE[1], values: daily.map((r) => r.ai), total: formatNumber(aiDays) }] }) +
        (d.ai_daily_since ? `<p class="muted chart-note">${escapeHtml(t("admChAiSince", { d: d.ai_daily_since }))}</p>` : ""),
    )}
    ${chartCard(
      `⚠️ ${t("admChJobs")}`,
      barChart({
        label: t("admChJobs"),
        labels: dLabels,
        series: [{ name: t("admChFailed"), color: "var(--danger)", values: daily.map((r) => r.jobs_failed), total: formatNumber(failed) }],
        empty: t("admChNoFailed"),
      }) + `<p class="muted chart-note">${escapeHtml(t("admChDone", { n: formatNumber(done) }))}</p>`,
    )}
  `,
  );
  bindCharts();
  document.querySelectorAll("[data-days]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      view.statDays = Number(node.getAttribute("data-days")) || 30;
      go("admin/stats");
    });
  });
}
