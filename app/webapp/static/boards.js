import { api, studentNames } from "./api.js";
import { nextMarkup } from "./next.js";
import { current, escapeHtml, setHtml, showError, skeleton, t } from "./ui.js";

export async function renderBoards(seq) {
  setHtml(skeleton("list"));
  try {
    const data = await api("/api/me/boards");
    const next = await nextMarkup();
    if (!current(seq)) return;
    paintStudy(data.boards || [], next);
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function paintStudy(boards, next) {
  const names = studentNames();
  const who = names.length ? names.join(", ") : t("studyGuest");
  const body = boards.length
    ? boards.map(one).join("")
    : `<div class="card muted">${escapeHtml(t("studyWait"))}</div>`;
  setHtml(`
    <div class="header"><h1>${escapeHtml(who)}</h1><p>${escapeHtml(t("studyLead"))}</p></div>
    ${next || ""}
    ${body}
  `);
}

function one(board) {
  const days = (board.weekdays || []).map((day) => t(`day${day}`)).join(", ");
  const level = board.level ? ` · ${board.level}` : "";
  const rows = (board.ranking || [])
    .map((item) => {
      const mine = item.mine ? " stu-paid" : "";
      return `<div class="stu-row${mine}"><div class="chat-name">${item.rank}. ${escapeHtml(item.name)}</div><span>${item.total}</span></div>`;
    })
    .join("");
  return `<div class="card">
    <div class="card-title">${board.today ? "● " : ""}${escapeHtml(board.name)}</div>
    <div class="stu-meta">${escapeHtml(board.today ? t("todayBadge") : days)} · ${escapeHtml(`${board.start}–${board.end}${level}`)}</div>
    ${rows || `<div class="stu-meta">${escapeHtml(t("rankEmpty"))}</div>`}
  </div>`;
}
