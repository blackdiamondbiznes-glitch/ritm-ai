import { api, haptic } from "./api.js";
import { escapeHtml, t, toast, withBusy } from "./ui.js";

/** The name students see. Empty means the Telegram name is shown. */
export function nameCard(data) {
  const own = (data && data.teacher_name) || "";
  const fallback = (data && data.telegram_name) || "";
  return `<div class="card">
    <div class="card-title">${escapeHtml(t("cabNameTitle"))}</div>
    <p class="stu-meta">${escapeHtml(t("cabNameLead"))}</p>
    <input class="input" id="cab-name" maxlength="80" autocomplete="off"
      value="${escapeHtml(own)}" placeholder="${escapeHtml(fallback)}">
    <button type="button" class="primary" id="cab-name-save">${escapeHtml(t("save"))}</button>
  </div>`;
}

export function bindNameCard() {
  const button = document.getElementById("cab-name-save");
  if (!button) return;
  button.addEventListener("click", (event) => {
    withBusy(event.currentTarget, saveName).catch((err) => toast(t(err.code || "error"), "err"));
  });
}

async function saveName() {
  const field = document.getElementById("cab-name");
  const data = await api("/api/tutor/name", {
    method: "POST",
    body: JSON.stringify({ name: field.value }),
  });
  field.value = data.teacher_name || "";
  haptic("success");
  toast(t("cabNameSaved"), "ok");
}
