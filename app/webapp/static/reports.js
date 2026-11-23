import { api, bootstrap, haptic, state } from "./api.js";
import { showLimit } from "./limits.js";
import { money } from "./money.js";
import { current, escapeHtml, setHtml, showError, skeleton, t, toast, withBusy } from "./ui.js";

/** Monthly report and the three Excel files. A lower plan sees the upgrade card. */
export async function renderReports(seq) {
  setHtml(skeleton("list"));
  const month = previousMonth();
  try {
    const data = await api(`/api/tutor/reports/monthly?month=${month}`);
    if (!current(seq)) return;
    paint(data, month);
  } catch (err) {
    if (!current(seq)) return;
    if (err && err.code === "export") {
      paintDenied(month);
      showLimit(err);
      return;
    }
    showError(err);
  }
}

function paint(data, month) {
  const rows = (data.groups || []).map((group) => groupCard(group, month)).join("");
  setHtml(`
    <div class="header"><h1>${escapeHtml(t("cabReport"))}</h1><p>${escapeHtml(t("repLead"))}</p></div>
    <p class="stu-meta">${escapeHtml(data.month || month)}</p>
    ${rows || `<div class="card muted">${escapeHtml(t("repNone"))}</div>`}
    <div class="card">
      <div class="stu-meta">${escapeHtml(t("repNew", { n: data.new_students || 0 }))}</div>
      <div class="stu-meta">${escapeHtml(t("repLeft", { n: data.left_students || 0 }))}</div>
    </div>
    ${exportButtons()}
  `);
  bindExports(month);
}

function paintDenied(month) {
  setHtml(`
    <div class="header"><h1>${escapeHtml(t("cabReport"))}</h1><p>${escapeHtml(t("repLead"))}</p></div>
    ${exportButtons()}
  `);
  bindExports(month);
}

function groupCard(group, month) {
  const rate = group.attendance_rate == null ? "—" : `${Math.round(group.attendance_rate * 100)}%`;
  return `<div class="card">
    <div class="card-title">${escapeHtml(group.name || "")}</div>
    <div class="stu-meta">${escapeHtml(t("repRate", { rate }))}</div>
    <div class="stu-meta">${escapeHtml(t("repCollected", { amount: money(group.collected_uzs) }))}</div>
    <div class="stu-meta">${escapeHtml(t("repOutstanding", { amount: money(group.outstanding_uzs) }))}</div>
    <button type="button" class="primary" data-att="${Number(group.group_id)}" data-month="${escapeHtml(month)}">${escapeHtml(t("expAttendance"))}</button>
  </div>`;
}

function exportButtons() {
  return `<button type="button" class="primary" id="exp-students">${escapeHtml(t("expStudents"))}</button>
    <button type="button" class="primary" id="exp-payments">${escapeHtml(t("expPayments"))}</button>`;
}

function bindExports(month) {
  document.getElementById("exp-students").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => download("/api/tutor/export/students.csv")).catch(fail);
  });
  document.getElementById("exp-payments").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => download(`/api/tutor/export/payments.csv?month=${month}`)).catch(fail);
  });
  document.querySelectorAll("[data-att]").forEach((node) => {
    node.addEventListener("click", (event) => {
      const id = node.getAttribute("data-att");
      const when = node.getAttribute("data-month");
      withBusy(event.currentTarget, () => download(`/api/tutor/export/attendance.csv?group_id=${id}&month=${when}`)).catch(fail);
    });
  });
}

function fail(err) {
  if (showLimit(err)) return;
  toast(t(err.code || "error"), "err");
}

/** Download with the session header. The token is never placed in the URL. */
async function download(path) {
  if (!state.token || Date.now() > state.tokenExp) await bootstrap();
  const res = await fetch(path, { headers: { Authorization: `Bearer ${state.token}` } });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const err = new Error(data.error || "error");
    err.code = data.error;
    err.status = res.status;
    err.data = data;
    throw err;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename(res.headers.get("Content-Disposition"));
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  haptic("success");
}

function filename(header) {
  const match = /filename="([^"]+)"/.exec(header || "");
  return match ? match[1] : "export.csv";
}

function previousMonth() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tashkent",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(new Date());
  const bag = {};
  for (const part of parts) bag[part.type] = part.value;
  const year = Number(bag.year);
  const month = Number(bag.month);
  const prev = month === 1 ? [year - 1, 12] : [year, month - 1];
  return `${prev[0]}-${String(prev[1]).padStart(2, "0")}`;
}
