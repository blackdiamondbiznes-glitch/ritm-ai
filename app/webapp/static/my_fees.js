import { api } from "./api.js";
import { money } from "./money.js";
import { escapeHtml, t } from "./ui.js";

export async function feeMarkup() {
  try {
    const data = await api("/api/me/fees");
    return (data.groups || []).map(card).join("");
  } catch {
    return "";
  }
}

function card(row) {
  if (row.amount == null) return "";
  const when = row.due_on ? row.due_on.split("-").reverse().join(".") : "";
  const next = t("feeNext", { amount: money(row.amount), date: when });
  const pack =
    row.lessons_total != null
      ? `<div class="stu-meta">${escapeHtml(t("feePack", { used: row.lessons_used || 0, total: row.lessons_total }))}</div>`
      : "";
  return `<div class="card"><div class="card-title">${escapeHtml(row.group_name || "")}</div>
    <div class="stu-meta">${escapeHtml(next)}</div>${pack}</div>`;
}
