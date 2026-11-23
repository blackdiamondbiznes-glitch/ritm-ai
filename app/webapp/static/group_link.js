import { state } from "./api.js";
import { escapeHtml, t, toast } from "./ui.js";

/** The group's sign-up link, with a copy button next to the post-to-chat one. */
export function linkCard(group) {
  const url = enrollUrl(group && group.enroll_code);
  if (!url) return "";
  return `<div class="card">
    <div class="card-title">${escapeHtml(t("grpLinkTitle"))}</div>
    <p class="stu-meta">${escapeHtml(t("grpLinkLead"))}</p>
    <input class="input" id="grp-url" readonly value="${escapeHtml(url)}">
    <button type="button" class="primary" id="grp-copy">${escapeHtml(t("grpLinkCopy"))}</button>
  </div>`;
}

export function bindLinkCard() {
  const button = document.getElementById("grp-copy");
  if (!button) return;
  button.addEventListener("click", async () => {
    const field = document.getElementById("grp-url");
    try {
      await navigator.clipboard.writeText(field.value);
      toast(t("stuLinkCopied"), "ok");
    } catch {
      field.focus();
      field.select();
      toast(t("stuLinkSelect"), "err");
    }
  });
}

function enrollUrl(code) {
  const name = state.me && state.me.bot_username;
  if (!name || !code) return "";
  return `https://t.me/${name}?start=enroll_${code}`;
}
