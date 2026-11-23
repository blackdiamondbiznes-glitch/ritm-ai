import { api } from "./api.js";
import { escapeHtml, t } from "./ui.js";

const TZ = "Asia/Tashkent";
const LABEL = {
  present: "attPresent",
  late: "attLate",
  absent: "attAbsent",
  excused: "attExcused",
};

export async function historyMarkup(boards) {
  const groups = (boards || []).filter((board) => board.group_id);
  if (!groups.length) return "";
  const cards = await Promise.all(groups.map((board) => oneGroup(board.group_id)));
  return cards.filter(Boolean).join("");
}

async function oneGroup(groupId) {
  try {
    const data = await api(`/api/me/attendance?group_id=${groupId}`);
    return card(data);
  } catch {
    return "";
  }
}

function card(data) {
  const marks = (data.marks || []).slice(0, 8);
  const rows = marks.length
    ? marks.map(line).join("")
    : `<div class="stu-meta">${escapeHtml(t("attNone"))}</div>`;
  return `<div class="card">
    <div class="card-title">${escapeHtml(t("attHistory"))}</div>
    <div class="stu-meta">${escapeHtml(data.group_name || "")} · ${escapeHtml(percent(data.rate))}</div>
    ${rows}
  </div>`;
}

function line(row) {
  const when = row.starts_at
    ? new Intl.DateTimeFormat("en-GB", {
        timeZone: TZ,
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).format(new Date(row.starts_at))
    : "";
  return `<div class="stu-row"><div class="chat-name">${escapeHtml(row.title || "")}</div>
    <span class="stu-meta">${escapeHtml(`${when} · ${t(LABEL[row.status] || "attNone")}`)}</span></div>`;
}

function percent(rate) {
  if (rate == null) return t("attNone");
  return t("attRate", { n: Math.round(rate * 100) });
}
