/* In-app payment on the Tarifim screen: plan + period -> offer -> code, exact amount and
   cards -> receipt upload. Prices, discounts and every rule come from the server
   (the same PaymentService as the bot); this file only draws and sends. */
import { api, apiForm, cached, forget, go, haptic, load, openTelegram, persist, remember, state } from "./api.js";
import { current, escapeHtml, formatNumber, setHtml, skeleton, t, toast, withBusy } from "./ui.js";
import { mirrorMainButton } from "./main_btn.js";

const OPTIONS = "/api/pay/options";
const MAX_BYTES = 10 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
const OPEN = ["pending", "disputed"];
const pick = { plan: "", months: 1, accept: false };

/** Draw the Tarifim screen. `ui` carries profile.js helpers (subHead, bindRows). */
export async function renderPlanPay(seq, ui) {
  const hit = cached(OPTIONS);
  if (hit) paint(hit, ui);
  else setHtml(`${ui.subHead(t("rowPlan"))}${headCard()}${skeleton("list")}`);
  try {
    const data = await load(OPTIONS, { maxAge: 0 });
    if (current(seq) && data !== hit) paint(data, ui);
  } catch (_err) {
    if (current(seq) && !hit) paint({ plans: [], cards: [], failed: true }, ui);
  }
}

function sync(data) {
  if (!state.dash || data.failed) return;
  const keep = ["plans", "discounts", "terms_version", "review_hours", "invoice", "submitted"];
  const plan = { ...(state.dash.plan || {}) };
  Object.keys(data).forEach((key) => {
    if (!keep.includes(key)) plan[key] = data[key];
  });
  state.dash.plan = plan;
  persist();
}

function paint(data, ui) {
  sync(data);
  const open = data.pending && OPEN.includes(data.pending.status) ? data.pending : null;
  let body;
  if (data.payments_blocked) body = `<div class="card"><p class="err">${escapeHtml(t("payBlockedNote"))}</p></div>`;
  else if (open) body = pendingCard(open, data);
  else if (data.invoice) body = invoiceCard(data);
  else if (data.plans && data.plans.length && data.cards && data.cards.length) body = pickerCard(data);
  else body = data.failed ? "" : `<div class="card muted">${escapeHtml(t("payUnconfigured"))}</div>`;
  const bot = state.me && state.me.bot_username
    ? `<button type="button" class="ghost wide" id="pay-bot">${escapeHtml(t("payBot"))}</button>`
    : "";
  setHtml(`${ui.subHead(t("rowPlan"))}${headCard()}${body}${bot}`);
  ui.bindRows();
  bindCopy();
  bind(data, ui);
}

function headCard() {
  const plan = (state.dash && state.dash.plan) || {};
  const kind = plan.kind === "trial" ? "trial" : plan.kind === "active" ? "active" : "free";
  const days = plan.days_left != null && plan.kind !== "free" ? `<p>${escapeHtml(t("daysLeft", { n: plan.days_left }))}</p>` : "";
  const left = plan.ai_left != null ? Number(plan.ai_left) : Math.max(0, Number(plan.ai_limit || 0) - Number(plan.ai_used || 0));
  const ai = plan.ai_limit != null ? `<p class="ai-left">${escapeHtml(t("aiLeft", { n: formatNumber(left) }))}</p>` : "";
  return `<div class="card">
    <div class="card-title">${escapeHtml(t("plan"))}</div>
    <div class="big">${escapeHtml(plan.plan_name || "—")}</div>
    <p>${escapeHtml(t(kind))}</p>${days}${ai}
  </div>`;
}

const som = (n) => `${formatNumber(n)} so\u2018m`;

function flow(step) {
  const keys = ["payFlow1", "payFlow2", "payFlow3", "payFlow4"];
  return `<ol class="flow" aria-label="${escapeHtml(t("payChoosePlan"))}">${keys
    .map((key, i) => {
      const n = i + 1;
      const cls = n === step ? "on" : n < step ? "done" : "";
      return `<li class="${cls}">${n}. ${escapeHtml(t(key))}</li>`;
    })
    .join("")}</ol>`;
}

function pickerCard(data) {
  const plans = data.plans;
  if (!plans.some((p) => p.code === pick.plan)) pick.plan = (plans.find((p) => p.code === "pro") || plans[0]).code;
  const plan = plans.find((p) => p.code === pick.plan);
  const period = plan.periods.find((p) => p.months === pick.months) || plan.periods[0];
  pick.months = period.months;
  const planBtns = plans
    .map((p) => `<button type="button" class="seg-btn${p.code === plan.code ? " on" : ""}" data-plan="${escapeHtml(p.code)}">${escapeHtml(p.name)}<br><small>${escapeHtml(formatNumber(p.monthly))}</small></button>`)
    .join("");
  const periodBtns = plan.periods
    .map((p) => `<button type="button" class="seg-btn${p.months === period.months ? " on" : ""}" data-months="${p.months}">${escapeHtml(t("payMonths", { n: p.months }))}${p.percent ? `<br><small>−${p.percent}%</small>` : ""}</button>`)
    .join("");
  const old = period.regular_total > period.amount ? `<span class="pay-old">${escapeHtml(som(period.regular_total))}</span>` : "";
  const save = period.savings ? `<p class="ok small-text">${escapeHtml(t("paySave", { p: period.percent, x: formatNumber(period.savings) }))}</p>` : "";
  const founder = plan.founder ? `<div class="founder-badge">${escapeHtml(t("payFounderBadge"))}</div>` : "";
  const facts = t("payPlanFacts", { c: plan.max_chats, a: formatNumber(plan.ai_limit) });
  return `<div class="card pay-pick">
    ${flow(1)}
    <div class="card-title">${escapeHtml(t("payChoosePlan"))}</div>
    <div class="seg">${planBtns}</div>
    <p class="muted small-text">${escapeHtml(facts)}</p>
    <div class="card-title">${escapeHtml(t("payChoosePeriod"))}</div>
    <div class="seg">${periodBtns}</div>
    ${founder}
    <div class="pay-total"><span class="muted">${escapeHtml(t("payTotal"))}</span><span>${old}<strong>${escapeHtml(som(period.amount))}</strong></span></div>
    ${period.months > 1 ? `<p class="muted small-text">${escapeHtml(t("payPerMonth", { x: formatNumber(period.per_month) }))}</p>` : ""}
    ${save}
    <label class="pay-check"><input type="checkbox" id="pay-accept"${pick.accept ? " checked" : ""} /> <span>${escapeHtml(t("payAccept"))}</span></label>
    <button type="button" class="link-btn" data-go="profile/terms">${escapeHtml(t("payTermsLink"))}</button>
    <button type="button" class="primary" id="pay-start"${pick.accept ? "" : " disabled"}>${escapeHtml(t("payContinue"))}</button>
  </div>`;
}

function invoiceCard(data) {
  const inv = data.invoice;
  const cards = (data.cards || [])
    .map((card) => copyRow(String(card.number).replace(/\s+/g, ""), card.number, `${card.type} · ${card.holder}`))
    .join("");
  return `${flow(3)}<div class="card">
    <div class="card-title">${escapeHtml(t("payInvoiceTitle", { plan: inv.plan_name, n: inv.months }))}</div>
    <p class="form-label">${escapeHtml(t("payStep1"))}</p>
    <div class="pay-ref">
      ${copyRow(String(inv.amount_uzs), som(inv.amount_uzs), t("payExact"))}
      ${copyRow(inv.ref, inv.ref, t("payRef"))}
      <p class="muted small-text">${escapeHtml(t("payExactHintApp"))}</p>
    </div>
    <div class="pay-cards">${cards}</div>
  </div>
  <div class="card pay-form" data-busy-group>
    <p class="form-label">${escapeHtml(t("payStep2"))}</p>
    <label class="field-label" for="pay-last4">${escapeHtml(t("payLast4"))}</label>
    <input class="input" id="pay-last4" inputmode="numeric" maxlength="4" autocomplete="off" placeholder="1234" />
    <label class="field-label" for="pay-when">${escapeHtml(t("payWhen"))}</label>
    <input class="input" id="pay-when" type="datetime-local" value="${tashkentNow()}" max="${tashkentNow()}" />
    <label class="field-label" for="pay-file">${escapeHtml(t("payReceipt"))}</label>
    <input class="input" id="pay-file" type="file" accept="${TYPES.join(",")}" />
    <p class="form-err" id="pay-err" hidden></p>
    <button type="button" class="primary" id="pay-submit">${escapeHtml(t("paySubmit"))}</button>
    <button type="button" class="ghost wide" id="pay-cancel">${escapeHtml(t("payChange"))}</button>
  </div>`;
}

function pendingCard(open, data) {
  const hint = open.status === "pending" ? t("payPendingHint", { h: data.review_hours || 12 }) : t("pst_disputed");
  return `<div class="card pay-wait">
    <div class="card-title">${escapeHtml(t("pst_pending"))}</div>
    ${copyRow(open.ref || `#${open.id}`, open.ref || `#${open.id}`, t("payRef"))}
    <p><strong>${escapeHtml(som(open.amount_uzs))}</strong> · ${escapeHtml(t("payMonths", { n: open.months }))}</p>
    <p class="muted small-text">${escapeHtml(hint)}</p>
    ${open.status === "pending" ? `<button type="button" class="ghost wide" id="pay-cancel">${escapeHtml(t("payCancelReq"))}</button>` : ""}
  </div>`;
}

function bind(data, ui) {
  const redraw = (next) => {
    remember(OPTIONS, next);
    forget("/api/me/payments");
    paint(next, ui);
  };
  document.querySelectorAll("[data-plan]").forEach((node) => {
    node.onclick = () => {
      haptic("light");
      pick.plan = node.getAttribute("data-plan");
      paint(data, ui);
    };
  });
  document.querySelectorAll("[data-months]").forEach((node) => {
    node.onclick = () => {
      haptic("light");
      pick.months = Number(node.getAttribute("data-months"));
      paint(data, ui);
    };
  });
  const accept = document.getElementById("pay-accept");
  const start = document.getElementById("pay-start");
  if (accept && start) {
    accept.onchange = () => {
      pick.accept = accept.checked;
      start.disabled = !accept.checked;
    };
    start.onclick = () =>
      withBusy(start, async () => {
        const body = { plan: pick.plan, months: pick.months, accept: pick.accept, terms_version: data.terms_version };
        try {
          redraw(await api("/api/pay/start", { method: "POST", body: JSON.stringify(body) }));
          haptic("success");
        } catch (err) {
          fail(err);
        }
      });
  }
  const cancel = document.getElementById("pay-cancel");
  if (cancel) {
    cancel.onclick = () =>
      withBusy(cancel, async () => {
        try {
          redraw(await api("/api/pay/cancel", { method: "POST", body: "{}" }));
        } catch (err) {
          fail(err);
        }
      });
  }
  const submit = document.getElementById("pay-submit");
  if (submit) submit.onclick = () => withBusy(submit, () => send(data, redraw));
  const bot = document.getElementById("pay-bot");
  if (bot) bot.onclick = () => openTelegram("");
  mirrorMainButton(start || submit);
}

async function send(data, redraw) {
  const last4 = (document.getElementById("pay-last4").value || "").replace(/\D/g, "");
  const when = document.getElementById("pay-when").value || "now";
  const file = (document.getElementById("pay-file").files || [])[0];
  if (last4.length !== 4) return inline("last4");
  if (!file) return inline("receipt");
  if (file.size > MAX_BYTES) return inline("too_large");
  if (file.type && !TYPES.includes(file.type)) return inline("bad_type");
  const form = new FormData();
  form.append("payment_id", String(data.invoice.id));
  form.append("last4", last4);
  form.append("when", when);
  form.append("receipt", file, file.name || "receipt");
  try {
    const next = await apiForm("/api/pay/submit", form);
    haptic("success");
    toast(t("paySent"));
    redraw(next);
  } catch (err) {
    if (err.status === 409 || err.code === "blocked") fail(err);
    else inline(err.code || "generic");
  }
  return undefined;
}

function inline(code) {
  haptic("error");
  const node = document.getElementById("pay-err");
  if (node) {
    node.textContent = errText(code);
    node.hidden = false;
  }
}

function fail(err) {
  haptic("error");
  toast(errText(err && err.code), "err");
  load(OPTIONS, { maxAge: 0 }).then(() => go("profile/plan")).catch(() => {});
}

function errText(code) {
  const key = `payErr_${code || "generic"}`;
  const text = t(key);
  return text === key ? t("payErr_generic") : text;
}

/** Tashkent wall clock (UTC+5, no DST) for the datetime-local default. */
function tashkentNow() {
  return new Date(Date.now() + 5 * 3600 * 1000).toISOString().slice(0, 16);
}

export function copyRow(value, shown, caption) {
  return `<button type="button" class="pay-card" data-copy="${escapeHtml(value)}">
    <span><div class="pay-card-num">${escapeHtml(shown)}</div><div class="pay-card-sub">${escapeHtml(caption)}</div></span>
    <span class="pay-copy">${escapeHtml(t("payCopy"))}</span>
  </button>`;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_err) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (_e) {
      ok = false;
    }
    area.remove();
    return ok;
  }
}

export function bindCopy() {
  document.querySelectorAll("[data-copy]").forEach((node) => {
    node.addEventListener("click", async () => {
      const ok = await copyText(node.getAttribute("data-copy"));
      haptic(ok ? "success" : "error");
      if (ok) toast(t("payCopied"));
    });
  });
}
