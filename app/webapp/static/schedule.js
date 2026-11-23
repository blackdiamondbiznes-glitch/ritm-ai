import { clockInput, readClock, readWhen, whenInput } from "./clock.js";
import { api, haptic } from "./api.js";
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

const TZ = "Asia/Tashkent";
const ERROR_KEY = {
  empty: "lesNameNeed",
  long: "lesNameLong",
  when: "lesWhenBad",
  time: "schTime",
  span: "schSpan",
  missing: "schMissing",
  slot: "schSlot",
  range: "schRange",
  choice: "error",
  note: "stuNoteLong",
  link: "lesLinkBad",
};
const STATUS_KEY = { scheduled: "lesScheduled", done: "lesDone", cancelled: "lesCancelled" };

let anchor = "";
let rows = [];
let openId = null;
let seq = 0;

export async function renderSchedule(token) {
  seq = token;
  if (!anchor) anchor = mondayOf(tashkentToday());
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
  const data = await api(`/api/tutor/sessions?from=${anchor}&to=${addDays(anchor, 13)}`);
  rows = Array.isArray(data) ? data : [];
}

function paint() {
  const row = openId == null ? null : rows.find((item) => item.id === openId);
  if (row) paintOne(row);
  else paintWeek();
}

function paintWeek() {
  const today = tashkentToday();
  const days = Array.from({ length: 14 }, (_, index) => addDays(anchor, index));
  setHtml(`
    ${cabinetSwitch("schedule")}
    <div class="header"><h1>${escapeHtml(t("schTitle"))}</h1><p>${escapeHtml(t("schLead"))}</p></div>
    <div class="week-nav">
      <button type="button" class="ghost" id="sch-prev">${escapeHtml(t("schPrev"))}</button>
      <button type="button" class="ghost" id="sch-next">${escapeHtml(t("schNext"))}</button>
    </div>
    ${days.map((iso) => dayCard(iso, iso === today)).join("")}
  `);
  bindCabinetSwitch();
  document.getElementById("sch-prev").addEventListener("click", () => shift(-7));
  document.getElementById("sch-next").addEventListener("click", () => shift(7));
  document.querySelectorAll("[data-session]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      openId = Number(node.getAttribute("data-session"));
      paint();
    });
  });
}

function dayCard(iso, today) {
  const list = rows.filter((row) => dayKey(row.starts_at) === iso);
  const items = list.length
    ? list.map(sessionButton).join("")
    : `<div class="stu-meta">${escapeHtml(t("schEmpty"))}</div>`;
  const mark = today ? " today" : "";
  const label = `${t(`day${weekday(iso)}`)} · ${iso.slice(8)}.${iso.slice(5, 7)}`;
  return `<div class="card week-day${mark}"><div class="card-title">${escapeHtml(label)}</div>${items}</div>`;
}

function sessionButton(row) {
  const who = row.group_name || t("schSolo");
  const tone = row.status === "cancelled" ? " les-cancelled" : row.status === "done" ? " les-done" : "";
  return `<button type="button" class="stu-row sch-row" data-session="${row.id}">
    <div class="chat-name${tone}">${escapeHtml(clock(row.starts_at))} ${escapeHtml(row.title)}</div>
    <span class="stu-meta">${escapeHtml(who)}</span>
  </button>`;
}

function paintOne(row) {
  const end = row.ends_at || plusMinutes(row.starts_at, 90);
  setHtml(`
    ${cabinetSwitch("schedule")}
    <div class="header"><h1>${escapeHtml(row.title)}</h1>
      <p>${escapeHtml(row.group_name || t("schSolo"))}</p></div>
    <div class="card">
      <label class="field"><span class="field-label">${escapeHtml(t("lesName"))}</span>
        <input class="input" id="sch-title" maxlength="120" value="${escapeHtml(row.title)}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("schWhen"))}</span>
        ${whenInput("sch-start", wall(row.starts_at))}</label>
      <label class="field"><span class="field-label">${escapeHtml(t("schEnd"))}</span>
        ${clockInput("sch-end-time", wall(end).slice(11, 16))}</label>
      <label class="field"><span class="field-label">${escapeHtml(t("lesLink"))}</span>
        <input class="input" id="sch-link" type="url" inputmode="url" maxlength="500" placeholder="https://zoom.us/j/…" value="${escapeHtml(row.meeting_url || "")}">
        <span class="form-hint">${escapeHtml(t("lesLinkHint"))}</span></label>
      <p class="stu-meta">${escapeHtml(t(STATUS_KEY[row.status] || "lesScheduled"))}</p>
      ${row.group_id ? `<a class="ghost att-back" href="#/cabinet/schedule/${row.id}/attendance">${escapeHtml(t("attNav"))}</a>` : ""}
      <button type="button" class="primary" id="sch-save">${escapeHtml(t("save"))}</button>
      <button type="button" class="ghost" id="sch-done">${escapeHtml(t("schDone"))}</button>
      <button type="button" class="ghost danger" id="sch-cancel">${escapeHtml(t("schCancel"))}</button>
      <button type="button" class="ghost" id="sch-back">${escapeHtml(t("schBack"))}</button>
    </div>
  `);
  bindCabinetSwitch();
  document.getElementById("sch-back").addEventListener("click", () => {
    openId = null;
    paint();
  });
  bindAction("sch-save", () =>
    send(row, {
      title: document.getElementById("sch-title").value,
      starts_at: readWhen("sch-start"),
      ends_at: endWall(readWhen("sch-start"), readClock("sch-end-time")),
      meeting_url: document.getElementById("sch-link").value.trim(),
    }),
  );
  bindAction("sch-done", () => send(row, { status: "done" }));
  bindAction("sch-cancel", () => send(row, { status: "cancelled" }));
}

function bindAction(id, work) {
  document.getElementById(id).addEventListener("click", (event) => {
    withBusy(event.currentTarget, work).catch((err) => toast(t(ERROR_KEY[err.code] || "error"), "err"));
  });
}

async function send(row, body) {
  await api(`/api/tutor/sessions/${row.id}`, { method: "PATCH", body: JSON.stringify(body) });
  haptic("success");
  toast(t("saved"), "ok");
  openId = null;
  await load();
  if (current(seq)) paint();
}

async function shift(days) {
  anchor = addDays(anchor, days);
  openId = null;
  try {
    await load();
    if (current(seq)) paint();
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function tashkentToday() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
}

function mondayOf(iso) {
  const date = atNoon(iso);
  const day = date.getUTCDay();
  date.setUTCDate(date.getUTCDate() + (day === 0 ? -6 : 1 - day));
  return date.toISOString().slice(0, 10);
}

function addDays(iso, count) {
  const date = atNoon(iso);
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0, 10);
}

function atNoon(iso) {
  return new Date(`${iso}T12:00:00+05:00`);
}

function weekday(iso) {
  const day = atNoon(iso).getUTCDay();
  return day === 0 ? 7 : day;
}

function wall(iso) {
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const pick = (type) => parts.find((part) => part.type === type).value;
  return `${pick("year")}-${pick("month")}-${pick("day")}T${pick("hour")}:${pick("minute")}`;
}

/** End time on the lesson's day. An end before the start belongs to the next day. */
function endWall(start, time) {
  if (!start || !time) return "";
  const day = time < start.slice(11, 16) ? addDays(start.slice(0, 10), 1) : start.slice(0, 10);
  return `${day}T${time}`;
}

function dayKey(iso) {
  return wall(iso).slice(0, 10);
}

function clock(iso) {
  return wall(iso).slice(11, 16);
}

function plusMinutes(iso, minutes) {
  return new Date(new Date(iso).getTime() + minutes * 60000).toISOString();
}
