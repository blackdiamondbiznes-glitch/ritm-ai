import { api, haptic } from "./api.js";
import { current, escapeHtml, setHtml, showError, skeleton, t, toast, withBusy } from "./ui.js";

const TZ = "Asia/Tashkent";
const STATES = [
  ["present", "attPresent"],
  ["late", "attLate"],
  ["absent", "attAbsent"],
  ["excused", "attExcused"],
];
const ERROR_KEY = {
  future: "attFuture",
  student: "attStudent",
  missing: "attMissing",
  choice: "error",
  note: "attNote",
  marks: "error",
};

let marks = new Map();

export async function renderRoll(seq) {
  const sessionId = Number(hashParts()[2]);
  setHtml(skeleton("list"));
  try {
    const data = await api(`/api/tutor/sessions/${sessionId}/attendance`);
    if (!current(seq)) return;
    marks = new Map((data.students || []).map((row) => [row.student_id, row.status]));
    paint(data, sessionId);
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function paint(data, sessionId) {
  const students = data.students || [];
  const future = isFuture(data.starts_at);
  const body = students.length
    ? students.map((row) => studentRow(row)).join("")
    : `<div class="card muted">${escapeHtml(t("attEmpty"))}</div>`;
  const tools = future
    ? `<div class="card err">${escapeHtml(t("attFuture"))}</div>`
    : `<button type="button" class="ghost" id="att-all">${escapeHtml(t("attAll"))}</button>
       <button type="button" class="primary" id="att-save">${escapeHtml(t("save"))}</button>`;
  setHtml(`
    <div class="header"><h1>${escapeHtml(t("attTitle"))}</h1>
      <p>${escapeHtml(data.group_name || "")} · ${escapeHtml(clock(data.starts_at))}</p></div>
    ${body}
    ${tools}
    <a class="ghost att-back" href="#/cabinet/schedule">${escapeHtml(t("schBack"))}</a>
  `);
  if (future) return;
  document.querySelectorAll("[data-student]").forEach((node) => {
    node.addEventListener("click", () => pick(node));
  });
  document.getElementById("att-all").addEventListener("click", () => {
    haptic("light");
    students.forEach((row) => marks.set(row.student_id, "present"));
    paint(data, sessionId);
  });
  document.getElementById("att-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => save(sessionId, students)).catch((err) => {
      toast(t(ERROR_KEY[err.code] || "error"), "err");
    });
  });
}

function studentRow(row) {
  const buttons = STATES.map(([status, key]) => {
    const on = marks.get(row.student_id) === status ? " on" : "";
    return `<button type="button" class="seg-btn${on}" data-student="${row.student_id}" data-status="${status}">${escapeHtml(t(key))}</button>`;
  }).join("");
  return `<div class="card att-row"><div class="chat-name">${escapeHtml(row.name)}</div>
    <div class="seg att-seg">${buttons}</div></div>`;
}

function pick(node) {
  haptic("light");
  const studentId = Number(node.getAttribute("data-student"));
  const status = node.getAttribute("data-status");
  marks.set(studentId, marks.get(studentId) === status ? null : status);
  const box = node.parentElement;
  box.querySelectorAll("[data-status]").forEach((button) => {
    button.classList.toggle("on", button.getAttribute("data-status") === marks.get(studentId));
  });
}

async function save(sessionId, students) {
  const body = {
    marks: students.map((row) => ({ student_id: row.student_id, status: marks.get(row.student_id) || "" })),
  };
  const data = await api(`/api/tutor/sessions/${sessionId}/attendance`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  haptic("success");
  toast(t("saved"), "ok");
  marks = new Map((data.students || []).map((row) => [row.student_id, row.status]));
  paint(data, sessionId);
}

function hashParts() {
  return (location.hash || "").replace(/^#\/?/, "").split("/").filter(Boolean);
}

function isFuture(iso) {
  if (!iso) return true;
  return wallDay(iso) > tashkentToday();
}

function tashkentToday() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
}

function wallDay(iso) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date(iso));
}

function clock(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(iso));
}
