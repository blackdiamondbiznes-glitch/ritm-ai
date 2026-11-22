import { api, go, haptic, isTutor, state } from "./api.js";
import {
  bindCabinetSwitch,
  cabinetSwitch,
  current,
  escapeHtml,
  formatNumber,
  setHtml,
  showError,
  skeleton,
  syncChrome,
  t,
  toast,
  withBusy,
} from "./ui.js";

export async function renderCabinet(seq) {
  if (!isTutor()) {
    paintEnable();
    return;
  }
  setHtml(skeleton("home"));
  try {
    const [data, groups] = await Promise.all([
      api("/api/tutor/summary"),
      api("/api/tutor/groups"),
    ]);
    if (!current(seq)) return;
    paint(data, groups.groups || []);
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function paintEnable() {
  setHtml(`
    <div class="header"><h1>${escapeHtml(t("cabEnable"))}</h1><p>${escapeHtml(t("cabEnableLead"))}</p></div>
    <button type="button" class="primary" id="cab-on">${escapeHtml(t("cabOn"))}</button>
  `);
  document.getElementById("cab-on").addEventListener("click", (event) => {
    withBusy(event.currentTarget, turnOn).catch((err) => toast(t(err.code || "error"), "err"));
  });
}

async function turnOn() {
  const data = await api("/api/tutor/enable", { method: "POST", body: "{}" });
  if (state.me && state.me.user) state.me.user.cabinet_niche = data.cabinet_niche || "tutor";
  syncChrome();
  haptic("success");
  paint(data);
}

function paint(data, groups = []) {
  const students = data.students || {};
  const lessons = data.lessons || {};
  setHtml(`
    ${cabinetSwitch("")}
    <div class="header"><h1>${escapeHtml(t("navCabinet"))}</h1><p>${escapeHtml(t("cabLead"))}</p></div>
    <div class="card-title">${escapeHtml(t("todayTitle"))}</div>
    ${todayRows(groups)}
    <div class="kpis">
      ${card("cabinet/students/paid", students.paid, "stuPaid")}
      ${card("cabinet/students/debtor", students.debtor, "stuDebtor")}
      ${card("cabinet/students/inactive", students.inactive, "stuInactive")}
    </div>
    <button type="button" class="card list-btn" data-go="cabinet/students/debtor">
      <div class="card-title">${escapeHtml(t("cabDebt"))}</div>
      <div class="big">${escapeHtml(t("stuSum", { n: formatNumber(students.debt_uzs || 0) }))}</div>
    </button>
    <button type="button" class="card list-btn" data-go="cabinet/lessons/scheduled">
      <div class="card-title">${escapeHtml(t("cabScheduled"))}</div>
      <div class="big">${escapeHtml(formatNumber(lessons.scheduled || 0))}</div>
    </button>
  `);
  bindCabinetSwitch();
  document.querySelectorAll("[data-go]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(node.getAttribute("data-go"));
    });
  });
}

function todayRows(groups) {
  const day = tashkentWeekday();
  const rows = (groups || [])
    .filter((group) => (group.weekdays || []).includes(day))
    .sort((a, b) => a.start.localeCompare(b.start));
  if (!rows.length) return `<div class="card muted">${escapeHtml(t("todayEmpty"))}</div>`;
  return rows
    .map(
      (group) => `<button type="button" class="card list-btn" data-go="cabinet/groups/${group.id}">
        <div class="stu-row"><div class="chat-name">${escapeHtml(group.name)}</div>
        <span class="stu-meta">${escapeHtml(group.start)}–${escapeHtml(group.end)}</span></div>
        <div class="stu-meta">${escapeHtml(group.level || t("todayTitle"))}</div>
      </button>`,
    )
    .join("");
}

function tashkentWeekday() {
  const name = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tashkent",
    weekday: "short",
  }).format(new Date());
  return { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 }[name] || 1;
}

function card(hash, value, key) {
  return `<button type="button" class="kpi" data-go="${hash}">
    <div class="kpi-value">${escapeHtml(formatNumber(value || 0))}</div>
    <div class="kpi-label">${escapeHtml(t(key))}</div>
  </button>`;
}
