import { api, haptic } from "./api.js";
import { showLimit } from "./limits.js";
import { money } from "./money.js";
import {
  bindCabinetSwitch,
  cabinetSwitch,
  current,
  escapeHtml,
  setHtml,
  showError,
  skeleton,
  t,
  toast,
  withBusy,
} from "./ui.js";

const FILTERS = [
  ["due", "feeDueFilter"],
  ["overdue", "feeOverdue"],
  ["paid", "feePaid"],
];
const METHODS = [
  ["cash", "feeCash"],
  ["card", "feeCard"],
  ["transfer", "feeTransfer"],
  ["other", "feeOther"],
];

let filter = "due";
let rows = [];
let summary = {};
let openId = null;

export async function renderFees(seq) {
  setHtml(skeleton("list"));
  try {
    await load();
    if (!current(seq)) return;
    openId = null;
    paint();
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

async function load() {
  const query = filter ? `?status=${filter}` : "";
  summary = await api("/api/tutor/fees/summary");
  rows = await api(`/api/tutor/invoices${query}`);
}

function paint() {
  const row = openId == null ? null : rows.find((item) => item.id === openId);
  if (row) paintPay(row);
  else paintList();
}

function paintList() {
  const chips = FILTERS.map(([id, key]) => {
    const on = id === filter ? " selected" : "";
    return `<button type="button" class="chip-btn${on}" data-filter="${id}">${escapeHtml(t(key))}</button>`;
  }).join("");
  const body = rows.length
    ? rows.map(invoiceButton).join("")
    : `<div class="card muted">${escapeHtml(t("feeEmpty"))}</div>`;
  setHtml(`
    ${cabinetSwitch("fees")}
    <div class="header"><h1>${escapeHtml(t("feeTitle"))}</h1><p>${escapeHtml(t("feeLead"))}</p></div>
    <div class="kpis">
      <div class="kpi"><div class="kpi-value">${escapeHtml(money(summary.outstanding_uzs))}</div>
        <div class="kpi-label">${escapeHtml(t("feeOutstanding"))}</div></div>
      <div class="kpi"><div class="kpi-value">${escapeHtml(String(summary.overdue_count || 0))}</div>
        <div class="kpi-label">${escapeHtml(t("feeOverdue"))}</div></div>
    </div>
    <p class="stu-meta">${escapeHtml(t("feeCollected"))}: ${escapeHtml(money(summary.collected_uzs))}</p>
    <div class="chips">${chips}</div>
    ${body}
  `);
  bindCabinetSwitch();
  document.querySelectorAll("[data-filter]").forEach((node) => {
    node.addEventListener("click", () => {
      filter = node.getAttribute("data-filter");
      load().then(paint).catch(showError);
    });
  });
  document.querySelectorAll("[data-invoice]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      openId = Number(node.getAttribute("data-invoice"));
      paint();
    });
  });
}

function invoiceButton(row) {
  const who = `${row.student_name || ""} · ${row.group_name || ""}`;
  return `<button type="button" class="card list-btn" data-invoice="${row.id}">
    <div class="chat-name">${escapeHtml(who)}</div>
    <div class="stu-meta">${escapeHtml(money(row.amount_uzs - row.paid_uzs))} · ${escapeHtml(row.due_on)}</div>
    <div class="stu-meta">${escapeHtml(t("feeAdd"))}</div>
  </button>`;
}

function paintPay(row) {
  const left = Math.max(0, row.amount_uzs - row.paid_uzs);
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tashkent" }).format(new Date());
  const methods = METHODS.map(([id, key], index) => {
    const on = index === 0 ? " selected" : "";
    return `<button type="button" class="chip-btn${on}" data-method="${id}">${escapeHtml(t(key))}</button>`;
  }).join("");
  setHtml(`
    ${cabinetSwitch("fees")}
    <div class="header"><h1>${escapeHtml(t("feeAdd"))}</h1>
      <p>${escapeHtml(row.student_name || "")}</p></div>
    <div class="card">
      <p class="stu-meta">${escapeHtml(money(left))}</p>
      <label class="field"><span class="field-label">${escapeHtml(t("feeAmount"))}</span>
        <input class="input" id="pay-amount" inputmode="numeric" value="${left}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("feeDate"))}</span>
        <input class="input" id="pay-date" type="date" value="${today}"></label>
      <div class="chips" id="pay-method">${methods}</div>
      <button type="button" class="primary" id="pay-save">${escapeHtml(t("save"))}</button>
      <button type="button" class="ghost" id="pay-back">${escapeHtml(t("schBack"))}</button>
    </div>
  `);
  bindCabinetSwitch();
  document.querySelectorAll("[data-method]").forEach((node) => {
    node.addEventListener("click", () => {
      document.querySelectorAll("[data-method]").forEach((chip) => chip.classList.toggle("selected", chip === node));
    });
  });
  document.getElementById("pay-back").addEventListener("click", () => {
    openId = null;
    paint();
  });
  document.getElementById("pay-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => save(row)).catch((err) => {
      if (!showLimit(err)) toast(t("error"), "err");
    });
  });
}

async function save(row) {
  const method = document.querySelector("[data-method].selected").getAttribute("data-method");
  await api(`/api/tutor/invoices/${row.id}/payments`, {
    method: "POST",
    body: JSON.stringify({
      amount_uzs: Number(document.getElementById("pay-amount").value || 0),
      paid_on: document.getElementById("pay-date").value,
      method,
    }),
  });
  haptic("success");
  toast(t("saved"), "ok");
  openId = null;
  await load();
  paint();
}
