import { escapeHtml, t } from "./ui.js";

/** The gradebook, ranking, topic list, and one group button. */
export function gradebookTable(data) {
  const topics = (data && data.topics) || [];
  const rows = (data && data.gradebook) || [];
  if (!topics.length || !rows.length) return `<div class="stu-meta">${escapeHtml(t("bookEmpty"))}</div>`;
  const head = topics.map((topic) => `<th>${escapeHtml(topic.title)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = (row.marks || [])
        .map((mark) => `<td>${mark === null || mark === undefined ? "·" : escapeHtml(String(mark))}</td>`)
        .join("");
      return `<tr><th>${escapeHtml(row.name)}</th>${cells}</tr>`;
    })
    .join("");
  return `<div class="book"><table><thead><tr><th></th>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function rankRows(rows) {
  if (!rows.length) return `<div class="stu-meta">${escapeHtml(t("rankEmpty"))}</div>`;
  return rows
    .map(
      (item) => `<div class="stu-row">
        <div class="chat-name">${item.rank}. ${escapeHtml(item.name)}</div>
        <span class="stu-meta">${item.total}</span>
      </div>`,
    )
    .join("");
}

export function topicRows(rows) {
  if (!rows.length) return `<div class="stu-meta">${escapeHtml(t("topEmpty"))}</div>`;
  return rows
    .map(
      (item) => `<button type="button" class="list-btn" data-topic="${item.id}">
        <div class="chat-name">${escapeHtml(item.title)}</div>
        <div class="stu-meta">${escapeHtml(item.held_on)} · ${item.graded}</div>
      </button>`,
    )
    .join("");
}

export function groupButton(group) {
  return `<button type="button" class="card list-btn" data-group="${group.id}">
    <div class="stu-row">
      <div class="chat-name">${escapeHtml(group.name)}</div>
      <span class="stu-meta">${escapeHtml(t("grpCount", { n: group.students }))}</span>
    </div>
    <div class="stu-meta">${escapeHtml(schedule(group))}</div>
  </button>`;
}

function schedule(group) {
  const days = (group.weekdays || []).map((day) => t(`day${day}`)).join(", ");
  const clock = `${group.start}–${group.end}`;
  return days ? `${days} · ${clock}` : clock;
}
