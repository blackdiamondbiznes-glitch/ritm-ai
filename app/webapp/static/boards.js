import { api } from "./api.js";
import { current, escapeHtml, setHtml, showError, skeleton, t } from "./ui.js";

export async function renderBoards(seq) {
  setHtml(skeleton("list"));
  try {
    const data = await api("/api/me/boards");
    if (!current(seq)) return;
    const boards = data.boards || [];
    const body = boards.length
      ? boards.map(one).join("")
      : `<div class="card muted">${escapeHtml(t("rankEmpty"))}</div>`;
    setHtml(`
      <div class="header"><h1>${escapeHtml(t("rankTitle"))}</h1><p>${escapeHtml(t("rankLead"))}</p></div>
      ${body}
    `);
  } catch (err) {
    if (current(seq)) showError(err);
  }
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
    <div class="card-title">${escapeHtml(board.name)}</div>
    <div class="stu-meta">${escapeHtml(`${days} · ${board.start}–${board.end}${level}`)}</div>
    ${rows || `<div class="stu-meta">${escapeHtml(t("rankEmpty"))}</div>`}
  </div>`;
}
