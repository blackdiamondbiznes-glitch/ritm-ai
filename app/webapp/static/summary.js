import { api, go, haptic, isTutor, state } from "./api.js";
import { mountUpgrade } from "./limits.js";
import { bindNameCard, nameCard } from "./teacher_name.js";
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
    const [data, groups, limits, lessons, asks] = await Promise.all([
      api("/api/tutor/summary"),
      api("/api/tutor/groups"),
      api("/api/tutor/limits"),
      api("/api/tutor/lessons"),
      api("/api/tutor/requests").catch(() => ({ requests: [] })),
    ]);
    if (!current(seq)) return;
    paint(data, groups.groups || [], limits, lessons.lessons || [], (asks.requests || []).length);
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
  const [groups, limits] = await Promise.all([
    api("/api/tutor/groups"),
    api("/api/tutor/limits"),
  ]);
  paint(data, groups.groups || [], limits);
}

function paint(data, groups = [], limits = null, lessonRows = [], asking = 0) {
  const students = data.students || {};
  const lessons = data.lessons || {};
  setHtml(`
    ${cabinetSwitch("")}
    <div class="header"><h1>${escapeHtml(t("navCabinet"))}</h1><p>${escapeHtml(t("cabLead"))}</p></div>
    ${requestsCard(asking)}
    ${planCard(limits)}
    <div class="card-title">${escapeHtml(t("todayTitle"))}</div>
    ${todayRows(groups)}
    ${todayRoll(lessonRows)}
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
    <button type="button" class="card list-btn" data-go="cabinet/reports">
      <div class="card-title">${escapeHtml(t("cabReport"))}</div>
    </button>
    ${nameCard(data)}
  `);
  bindCabinetSwitch();
  bindNameCard();
  if (atCap(limits)) mountUpgrade();
  document.querySelectorAll("[data-go]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(node.getAttribute("data-go"));
    });
  });
}

function requestsCard(count) {
  if (!count) return "";
  return `<button type="button" class="card list-btn req-badge" data-go="cabinet/groups">
    <div class="stu-row"><div class="card-title">${escapeHtml(t("reqBadge", { n: count }))}</div><span class="badge-dot">${count}</span></div>
    <div class="stu-meta">${escapeHtml(t("reqBadgeLead"))}</div>
  </button>`;
}

function todayRoll(lessons) {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tashkent" }).format(new Date());
  const row = (lessons || []).find(
    (item) => item.group_id && item.starts_at && item.starts_at.slice(0, 10) === today && item.status !== "cancelled",
  );
  if (!row) return "";
  return `<button type="button" class="card list-btn" data-go="cabinet/schedule/${row.id}/attendance">
    <div class="card-title">${escapeHtml(t("attToday"))}</div>
    <div class="stu-meta">${escapeHtml(row.group_name || row.title || "")}</div>
  </button>`;
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

function planCard(limits) {
  if (!limits) return "";
  const names = { free: "Free", start: "Start", pro: "Pro", agency: "Ultra" };
  const extra = limits.kind === "trial" ? ` (${t("trial")})` : "";
  return `<div class="card" id="cab-usage">
    <div class="card-title">${escapeHtml(t("cabPlan", { name: names[limits.plan] || limits.plan, extra }))}</div>
    ${bar("grpNav", limits.groups)}
    ${bar("stuTitle", limits.students)}
    ${bar("remTitle", limits.notifications)}
  </div>`;
}

function bar(key, row) {
  const used = row ? row.used : 0;
  const limit = row ? row.limit : 0;
  const width = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const cap = limit < 0 ? "∞" : String(limit);
  return `<div class="stu-meta">${escapeHtml(t(key))} ${used}/${cap}</div><div class="bar"><span style="width:${width}%"></span></div>`;
}

function pair(row) {
  const used = row ? row.used : 0;
  const cap = row && row.limit < 0 ? "∞" : String(row ? row.limit : 0);
  return `${used}/${cap}`;
}

function atCap(limits) {
  const groups = limits && limits.groups;
  return Boolean(groups && groups.limit > 0 && groups.used >= groups.limit);
}

function card(hash, value, key) {
  return `<button type="button" class="kpi" data-go="${hash}">
    <div class="kpi-value">${escapeHtml(formatNumber(value || 0))}</div>
    <div class="kpi-label">${escapeHtml(t(key))}</div>
  </button>`;
}
