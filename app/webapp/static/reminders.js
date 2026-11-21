import { api, go, haptic, tg } from "./api.js";
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

const ERROR_KEY = {
  empty: "remTextNeed",
  long: "remTextLong",
  when: "lesWhenBad",
  student: "lesStudentBad",
  missing: "remMissing",
};

let cache = null;

export async function renderReminders(seq) {
  const place = reminderPlace();
  try {
    if (!cache || place.mode === "list") {
      setHtml(skeleton("list"));
      cache = await api("/api/tutor/reminders");
    }
    if (!current(seq)) return;
    if (place.mode === "new") paintForm();
    else paintList();
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function reminderPlace() {
  const parts = (location.hash || "").replace(/^#\/?/, "").split("/").filter(Boolean);
  return { mode: parts[2] === "new" ? "new" : "list" };
}

function paintList() {
  const rows = cache.reminders || [];
  const body = rows.length
    ? rows.map(rowButton).join("")
    : `<div class="card muted">${escapeHtml(t("remEmpty"))}</div>`;
  setHtml(`
    ${cabinetSwitch("reminders")}
    <div class="header"><h1>${escapeHtml(t("remTitle"))}</h1><p>${escapeHtml(t("remLead"))}</p></div>
    ${body}
    <button type="button" class="primary" id="rem-add">${escapeHtml(t("remAdd"))}</button>
  `);
  bindCabinetSwitch();
  document.querySelectorAll("[data-forget]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      withBusy(node, () => destroy(Number(node.getAttribute("data-forget")))).catch((err) => {
        toast(t(ERROR_KEY[err.code] || "error"), "err");
      });
    });
  });
  document.getElementById("rem-add").addEventListener("click", () => {
    haptic("light");
    go("cabinet/reminders/new");
  });
}

function paintForm() {
  const options = [`<option value="">${escapeHtml(t("lesNoStudent"))}</option>`]
    .concat(
      (cache.students || []).map(
        (student) => `<option value="${student.id}">${escapeHtml(student.name)}</option>`,
      ),
    )
    .join("");
  setHtml(`
    <div class="header"><h1>${escapeHtml(t("remAdd"))}</h1></div>
    <div class="card">
      <label class="field"><span class="field-label">${escapeHtml(t("remText"))}</span>
        <textarea class="input" id="rem-text" maxlength="300" rows="3"></textarea></label>
      <label class="field"><span class="field-label">${escapeHtml(t("lesStudent"))}</span>
        <select class="input" id="rem-student">${options}</select></label>
      <label class="field"><span class="field-label">${escapeHtml(t("lesWhen"))}</span>
        <input class="input" id="rem-when" type="datetime-local"></label>
      <button type="button" class="primary" id="rem-save">${escapeHtml(t("save"))}</button>
    </div>
  `);
  document.getElementById("rem-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, save).catch((err) => toast(t(ERROR_KEY[err.code] || "error"), "err"));
  });
}

async function save() {
  const studentRaw = document.getElementById("rem-student").value;
  const body = {
    text: document.getElementById("rem-text").value,
    student_id: studentRaw ? Number(studentRaw) : null,
    send_at: document.getElementById("rem-when").value,
  };
  cache = await api("/api/tutor/reminders", { method: "POST", body: JSON.stringify(body) });
  haptic("success");
  toast(t("saved"), "ok");
  go("cabinet/reminders");
}

async function destroy(id) {
  const yes = await ask(t("remDeleteAsk"));
  if (!yes) return;
  cache = await api(`/api/tutor/reminders/${id}`, { method: "DELETE" });
  haptic("success");
  go("cabinet/reminders");
}

function ask(text) {
  if (tg && tg.showConfirm) return new Promise((resolve) => tg.showConfirm(text, resolve));
  return Promise.resolve(window.confirm(text));
}

function rowButton(row) {
  const who = row.student_name ? escapeHtml(row.student_name) : escapeHtml(t("lesNoStudent"));
  const state = row.sent ? t("remSent") : t("remWaiting");
  return `<div class="card">
    <div class="stu-row">
      <div class="chat-name">${escapeHtml(row.text)}</div>
      <button type="button" class="ghost" data-forget="${row.id}">${escapeHtml(t("stuDelete"))}</button>
    </div>
    <div class="stu-meta">${who} · ${escapeHtml(formatWhen(row.send_at))} · ${escapeHtml(state)}</div>
  </div>`;
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
