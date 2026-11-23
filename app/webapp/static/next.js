import { api } from "./api.js";
import { icon } from "./icons.js";
import { escapeHtml, t } from "./ui.js";

const TZ = "Asia/Tashkent";

export async function nextMarkup() {
  try {
    const rows = await api("/api/me/sessions?days=14");
    return nextCard(Array.isArray(rows) ? rows : []);
  } catch {
    return "";
  }
}

export function nextCard(rows) {
  const upcoming = pickNext(rows);
  const body = upcoming.length
    ? upcoming.map(one).join("")
    : `<div class="stu-meta">${escapeHtml(t("nextEmpty"))}</div>`;
  return `<div class="card"><div class="card-title">${escapeHtml(t("nextTitle"))}</div>${body}</div>`;
}

function pickNext(rows) {
  const now = Date.now();
  const best = new Map();
  rows.forEach((row) => {
    if (!row.group_id || row.status === "cancelled") return;
    const end = Date.parse(row.ends_at || row.starts_at);
    if (Number.isNaN(end) || end < now) return;
    const prev = best.get(row.group_id);
    if (!prev || Date.parse(row.starts_at) < Date.parse(prev.starts_at)) best.set(row.group_id, row);
  });
  return [...best.values()].sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at));
}

function one(row) {
  const when = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(row.starts_at));
  const teacher = row.teacher_name ? ` · ${row.teacher_name}` : "";
  return `<div class="stu-row"><div>
    <div class="chat-name">${escapeHtml(row.group_name || row.title)}</div>
    <div class="stu-meta">${escapeHtml(`${when}${teacher}`)}</div>
  </div></div>${join(row.meeting_url)}`;
}

function join(url) {
  if (!url) return "";
  return `<button type="button" class="primary join-btn" data-open-url="${escapeHtml(url)}">${icon("video")}<span>${escapeHtml(t("learnJoin"))}</span></button>`;
}
