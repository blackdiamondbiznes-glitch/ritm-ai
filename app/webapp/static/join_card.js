import { api, bootstrap, go, haptic } from "./api.js";
import { escapeHtml, t, toast, withBusy } from "./ui.js";

/** A student who has no teacher yet types the code or pastes the link the teacher sent. */
export function joinCard() {
  return `<div class="card" id="join-card">
    <div class="card-title">🎓 ${escapeHtml(t("joinTitle"))}</div>
    <p class="stu-meta">${escapeHtml(t("joinLead"))}</p>
    <input class="input" id="join-code" maxlength="200" autocomplete="off" placeholder="${escapeHtml(t("joinPlaceholder"))}">
    <button type="button" class="primary" id="join-send">${escapeHtml(t("joinSend"))}</button>
    <p class="stu-meta join-result" id="join-result" hidden></p>
  </div>`;
}

export function bindJoin() {
  const button = document.getElementById("join-send");
  if (!button) return;
  button.addEventListener("click", (event) => {
    withBusy(event.currentTarget, send).catch(() => toast(t("error"), "err"));
  });
}

async function send() {
  const input = document.getElementById("join-code");
  const code = input.value.trim();
  input.classList.toggle("bad", !code);
  if (!code) {
    toast(t("joinNeed"), "err");
    return;
  }
  const data = await api("/api/me/join", { method: "POST", body: JSON.stringify({ code }) });
  const box = document.getElementById("join-result");
  box.hidden = false;
  box.textContent = data.text || "";
  input.classList.toggle("bad", !data.ok);
  if (!data.ok) return;
  haptic("success");
  await bootstrap();
  go("study");
}
