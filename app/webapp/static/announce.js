import { api, haptic, state } from "./api.js";
import { escapeHtml, t, toast } from "./ui.js";

export function announceBlock() {
  const chats = (state.dash && state.dash.chats) || [];
  if (!chats.length) {
    return `<div class="card"><p class="stu-meta">${escapeHtml(t("grpSendNone"))}</p>
      <button type="button" class="primary" id="grp-connect">${escapeHtml(t("grpConnect"))}</button></div>`;
  }
  const options = chats
    .map((chat) => `<option value="${chat.id}">${escapeHtml(chat.title || "")}</option>`)
    .join("");
  return `<div class="card">
    <div class="card-title">${escapeHtml(t("grpSend"))}</div>
    <p class="stu-meta">${escapeHtml(t("grpSendLead"))}</p>
    <select class="input" id="grp-chat">${options}</select>
    <button type="button" class="primary" id="grp-send">${escapeHtml(t("grpSend"))}</button>
  </div>`;
}

export async function announce(groupId) {
  const chatId = Number(document.getElementById("grp-chat").value);
  await api(`/api/tutor/groups/${groupId}/announce`, {
    method: "POST",
    body: JSON.stringify({ chat_id: chatId }),
  });
  haptic("success");
  toast(t("grpSendOk"), "ok");
}
