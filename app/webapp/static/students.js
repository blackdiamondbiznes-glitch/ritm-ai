import { api, go, haptic, state, tg } from "./api.js";
import { showLimit } from "./limits.js";
import { paintStudentForm } from "./student_form.js";
import { current, escapeHtml, formatNumber, setHtml, showError, skeleton, t, toast, withBusy } from "./ui.js";

const STATUSES = ["paid", "debtor", "inactive"];
const STATUS_KEY = { paid: "stuPaid", debtor: "stuDebtor", inactive: "stuInactive" };
const ERROR_KEY = {
  empty: "stuNameNeed",
  long: "stuNameLong",
  note: "stuNoteLong",
  phone: "stuPhoneBad",
  amount: "stuAmountBad",
  choice: "error",
  missing: "stuMissing",
  group: "stuGroupNeed",
};
let cache = null;
let filter = "all";
let catalog = [];

export async function renderStudents(sub, id, seq) {
  const place = studentPlace(sub, id);
  try {
    if (place.mode === "profile") {
      setHtml(skeleton("list"));
      const profile = await api(`/api/tutor/students/${place.id}`);
      if (!current(seq)) return;
      paintProfile(profile);
      return;
    }
    if (!cache || place.mode === "list") {
      setHtml(skeleton("list"));
      cache = await api("/api/tutor/students");
    }
    if (place.mode === "new" || place.mode === "edit") {
      setHtml(skeleton("list"));
      const listed = await api("/api/tutor/groups");
      catalog = listed.groups || [];
      if (!current(seq)) return;
      if (place.mode === "edit") {
        const profile = await api(`/api/tutor/students/${place.id}`);
        if (!current(seq)) return;
        paintStudentForm(profile.student, (profile.groups || []).map((group) => group.id), catalog, hooks());
      } else paintStudentForm(null, [], catalog, hooks());
      return;
    }
    if (!current(seq)) return;
    else {
      filter = place.filter;
      paintList();
    }
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function studentPlace(sub, id) {
  const parts = (location.hash || "").replace(/^#\/?/, "").split("/").filter(Boolean);
  const third = parts[2] || "";
  const fourth = parts[3] || "";
  if (sub === "new" || third === "new") return { mode: "new" };
  if (id && fourth === "edit") return { mode: "edit", id };
  if (id) return { mode: "profile", id };
  if (STATUSES.includes(third)) return { mode: "list", filter: third };
  return { mode: "list", filter: "all" };
}

const LESSON_KEY = { scheduled: "lesScheduled", done: "lesDone", cancelled: "lesCancelled" };

function paintProfile(data) {
  const row = data.student;
  const lessons = data.lessons || [];
  const reminders = data.reminders || [];
  const phone = row.phone ? escapeHtml(row.phone) : escapeHtml(t("stuNoPhone"));
  const note = row.note ? `<div class="card"><div class="stu-meta">${escapeHtml(row.note)}</div></div>` : "";
  const groupNames = (data.groups || []).map((group) => group.name).join(", ");
  const groupCard = `<div class="card"><div class="card-title">${escapeHtml(t("stuGroups"))}</div><div class="stu-meta">${escapeHtml(groupNames || t("stuNoGroups"))}</div></div>`;
  const lessonBody = lessons.length
    ? lessons.map(lessonRow).join("")
    : `<div class="stu-meta">${escapeHtml(t("stuNoLessons"))}</div>`;
  const reminderBody = reminders.length
    ? reminders.map(reminderRow).join("")
    : `<div class="stu-meta">${escapeHtml(t("stuNoReminders"))}</div>`;
  setHtml(`
    <div class="header">
      <h1>${escapeHtml(row.name)}</h1>
      <p>${escapeHtml(t(STATUS_KEY[row.status] || "stuMissing"))}</p>
    </div>
    <div class="card">
      <div class="stu-meta">${phone}</div>
      <div class="big">${escapeHtml(moneyLine(row))}</div>
    </div>
    ${note}
    ${groupCard}
    <div class="card">
      <div class="card-title">${escapeHtml(t("stuLessons"))}</div>
      ${lessonBody}
      <button type="button" class="primary" id="stu-lesson">${escapeHtml(t("lesAdd"))}</button>
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("stuReminders"))}</div>
      ${reminderBody}
    </div>
    ${joinButton(row)}
    <button type="button" class="primary" id="stu-edit">${escapeHtml(t("stuEdit"))}</button>
    <button type="button" class="ghost danger" id="stu-delete">${escapeHtml(t("stuDelete"))}</button>
  `);
  document.querySelectorAll("[data-lesson]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(`cabinet/lessons/${node.getAttribute("data-lesson")}`);
    });
  });
  document.getElementById("stu-lesson").addEventListener("click", () => {
    haptic("light");
    go(`cabinet/lessons/new/${row.id}`);
  });
  const link = document.getElementById("stu-link");
  if (link) {
    link.addEventListener("click", async () => {
      const field = document.getElementById("stu-url");
      const url = field ? field.value : joinUrl(row.join_code);
      try {
        await navigator.clipboard.writeText(url);
        toast(t("stuLinkCopied"), "ok");
      } catch {
        field.focus();
        field.select();
        toast(t("stuLinkSelect"), "err");
      }
    });
  }
  document.getElementById("stu-edit").addEventListener("click", () => {
    haptic("light");
    go(`cabinet/students/${row.id}/edit`);
  });
  document.getElementById("stu-delete").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => destroy(row.id)).catch((err) => (showLimit(err) ? null : toast(t(ERROR_KEY[err.code] || "error"), "err")));
  });
}

function joinButton(row) {
  const url = joinUrl(row.join_code);
  if (!url) return "";
  return `<div class="card">
    <div class="card-title">${escapeHtml(t("stuLink"))}</div>
    <input class="input" id="stu-url" readonly value="${escapeHtml(url)}">
    <p class="stu-meta">${escapeHtml(t("stuLinkHint"))}</p>
    <button type="button" class="primary" id="stu-link">${escapeHtml(t("stuLinkCopy"))}</button>
  </div>`;
}

function joinUrl(code) {
  const name = state.me && state.me.bot_username;
  if (!name || !code) return "";
  return `https://t.me/${name}?start=join_${code}`;
}

function lessonRow(row) {
  const when = row.starts_at ? ` · ${escapeHtml(formatWhen(row.starts_at))}` : "";
  return `<button type="button" class="list-btn" data-lesson="${row.id}">
    <div class="stu-row">
      <div class="chat-name">${escapeHtml(row.title)}</div>
      <span class="stu-badge les-${row.status}">${escapeHtml(t(LESSON_KEY[row.status] || "lesScheduled"))}</span>
    </div>
    <div class="stu-meta">${escapeHtml(t("stuSum", { n: formatNumber(row.amount_uzs) }))}${when}</div>
  </button>`;
}

function reminderRow(row) {
  const state = row.sent ? t("remSent") : t("remWaiting");
  return `<div class="stu-meta">${escapeHtml(row.text)} · ${escapeHtml(formatWhen(row.send_at))} · ${escapeHtml(state)}</div>`;
}

function formatWhen(iso) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Tashkent",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const pick = (type) => parts.find((part) => part.type === type).value;
  return `${pick("day")}.${pick("month")} ${pick("hour")}:${pick("minute")}`;
}

function paintEdit(id) {
  const row = (cache.students || []).find((item) => item.id === id);
  if (!row) {
    setHtml(`<div class="card err">${escapeHtml(t("stuMissing"))}</div>`);
    return;
  }
  paintStudentForm(row, undefined, catalog, hooks());
}

function hooks() {
  return { saved(data) { cache = data; }, remove: destroy };
}

function paintList() {
  const counts = cache.counts || { paid: 0, debtor: 0, inactive: 0 };
  const rows = (cache.students || []).filter((item) => filter === "all" || item.status === filter);
  const chips = ["all", ...STATUSES]
    .map((status) => {
      const label = status === "all" ? t("stuAll") : t(STATUS_KEY[status]);
      const on = status === filter ? " selected" : "";
      return `<button type="button" class="chip-btn${on}" data-filter="${status}">${escapeHtml(label)}</button>`;
    })
    .join("");
  const body = rows.length
    ? rows.map(rowButton).join("")
    : `<div class="card muted">${escapeHtml(t((cache.students || []).length ? "stuFilterEmpty" : "stuEmpty"))}</div>`;
  setHtml(`
    <div class="header"><h1>${escapeHtml(t("stuTitle"))}</h1><p>${escapeHtml(t("stuLead"))}</p></div>
    <div class="kpis">
      ${kpi(counts.paid, "stuPaid")}
      ${kpi(counts.debtor, "stuDebtor")}
      ${kpi(counts.inactive, "stuInactive")}
    </div>
    <div class="chips chips-scroll">${chips}</div>
    ${body}
    <button type="button" class="primary" id="stu-add">${escapeHtml(t("stuAdd"))}</button>
  `);
  document.querySelectorAll("[data-filter]").forEach((node) => {
    node.addEventListener("click", () => {
      filter = node.getAttribute("data-filter");
      haptic("light");
      paintList();
    });
  });
  document.querySelectorAll("[data-student]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(`cabinet/students/${node.getAttribute("data-student")}`);
    });
  });
  document.getElementById("stu-add").addEventListener("click", () => {
    haptic("light");
    go("cabinet/students/new");
  });
}

async function destroy(id) {
  const yes = await ask(t("stuDeleteAsk"));
  if (!yes) return;
  cache = await api(`/api/tutor/students/${id}`, { method: "DELETE" });
  haptic("success");
  toast(t("saved"), "ok");
  go("cabinet/students");
}

function ask(text) {
  if (tg && tg.showConfirm) return new Promise((resolve) => tg.showConfirm(text, resolve));
  return Promise.resolve(window.confirm(text));
}

function rowButton(row) {
  const phone = row.phone ? ` · ${row.phone}` : "";
  const note = row.note ? `<div class="stu-meta">${escapeHtml(row.note)}</div>` : "";
  return `<button type="button" class="card list-btn" data-student="${row.id}">
    <div class="stu-row">
      <div class="chat-name">${escapeHtml(row.name)}</div>
      <span class="stu-badge stu-${row.status}">${escapeHtml(t(STATUS_KEY[row.status]))}</span>
    </div>
    <div class="stu-meta">${escapeHtml(moneyLine(row))}${escapeHtml(phone)}</div>
    ${note}
  </button>`;
}

/** A card with no debt and no amount says so, instead of "Paid 0 so‘m". */
function moneyLine(row) {
  if (!row.amount_uzs) return t("learnFeeNone");
  return t("stuSum", { n: formatNumber(row.amount_uzs) });
}

function kpi(value, key) {
  return `<div class="kpi"><div class="kpi-value">${escapeHtml(formatNumber(value))}</div>
    <div class="kpi-label">${escapeHtml(t(key))}</div></div>`;
}
