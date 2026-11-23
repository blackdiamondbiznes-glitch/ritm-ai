import { escapeHtml } from "./ui.js";

/** 24-hour time as text: native time pickers show AM/PM on some phones. */
export function clockInput(id, value) {
  return `<input class="input" id="${id}" inputmode="numeric" maxlength="5" placeholder="18:30" autocomplete="off" value="${escapeHtml(value || "")}">`;
}

/** A date picker plus a 24-hour clock. `wall` is "YYYY-MM-DDTHH:MM" in Tashkent time. */
export function whenInput(id, wall) {
  const day = wall ? wall.slice(0, 10) : "";
  const time = wall ? wall.slice(11, 16) : "";
  return `<span class="when-row">
    <input class="input" id="${id}-day" type="date" value="${escapeHtml(day)}">
    ${clockInput(`${id}-time`, time)}
  </span>`;
}

/** "9:30", "930" and "09.30" become "09:30". A bad value is marked and returned as typed. */
export function readClock(id) {
  const node = document.getElementById(id);
  const raw = node ? node.value.trim() : "";
  const digits = raw.replace(/[^0-9]/g, "");
  const match = raw.match(/^(\d{1,2})[:.\s](\d{2})$/) || (digits.length >= 3 && digits.length <= 4 ? [raw, digits.slice(0, -2), digits.slice(-2)] : null);
  const hour = match ? Number(match[1]) : NaN;
  const minute = match ? Number(match[2]) : NaN;
  const ok = hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
  if (node) node.classList.toggle("bad", !ok && raw !== "");
  if (!ok) return raw;
  const text = `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  if (node) node.value = text;
  return text;
}

/** The pair from whenInput as "YYYY-MM-DDTHH:MM", or "" when the date is empty. */
export function readWhen(id) {
  const day = document.getElementById(`${id}-day`);
  if (!day || !day.value) return "";
  const time = readClock(`${id}-time`) || "00:00";
  return `${day.value}T${time}`;
}
