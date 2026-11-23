import { api, haptic } from "./api.js";
import { groupTabs } from "./group_tabs.js";
import { current, escapeHtml, setHtml, showError, skeleton, t, toast, withBusy } from "./ui.js";

const MINUTES = [
  ["", "noticeOff"],
  ["15", "noticeMin15"],
  ["30", "noticeMin30"],
  ["60", "noticeMin60"],
  ["120", "noticeMin120"],
];
const DAYS = [
  ["", "noticeOff"],
  ["1", "noticeDay1"],
  ["3", "noticeDay3"],
  ["7", "noticeDay7"],
];

export async function renderNotice(seq) {
  const groupId = Number(hashParts()[2]);
  setHtml(skeleton("list"));
  try {
    const [opened, notice] = await Promise.all([
      api(`/api/tutor/groups/${groupId}`),
      api(`/api/tutor/groups/${groupId}/notify`),
    ]);
    if (!current(seq)) return;
    paint(opened.group, notice, groupId);
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function paint(group, notice, groupId) {
  const chats = notice.chats || [];
  const options = [`<option value="">${escapeHtml(t("noticeChatNone"))}</option>`]
    .concat(
      chats.map((chat) => {
        const on = Number(chat.id) === Number(notice.chat_id) ? " selected" : "";
        return `<option value="${Number(chat.id)}"${on}>${escapeHtml(chat.title || "")}</option>`;
      }),
    )
    .join("");
  const checked = notice.fee_in_group ? " checked" : "";
  setHtml(`
    ${groupTabs(group, "notice")}
    <div class="card">
      <label class="field"><span class="field-label">${escapeHtml(t("noticeLesson"))}</span>
        <select class="input" id="notice-lesson">${choices(MINUTES, notice.remind_lesson_min)}</select></label>
      <label class="field"><span class="field-label">${escapeHtml(t("noticeFee"))}</span>
        <select class="input" id="notice-fee">${choices(DAYS, notice.remind_fee_days)}</select></label>
      <label class="field"><input type="checkbox" id="notice-public"${checked}> ${escapeHtml(t("noticeFeeGroup"))}</label>
      <label class="field"><span class="field-label">${escapeHtml(t("noticeChat"))}</span>
        <select class="input" id="notice-chat">${options}</select></label>
      <button type="button" class="primary" id="notice-save">${escapeHtml(t("save"))}</button>
    </div>
    <button type="button" class="primary" id="notice-open">${escapeHtml(t("noticeAnnounce"))}</button>
    <div class="card" id="notice-sheet" hidden>
      <label class="field"><span class="field-label">${escapeHtml(t("noticeText"))}</span>
        <textarea class="input" id="notice-text" maxlength="1000"></textarea></label>
      <label class="field"><input type="checkbox" id="notice-to-chat" checked> ${escapeHtml(t("noticeToChat"))}</label>
      <label class="field"><input type="checkbox" id="notice-to-students" checked> ${escapeHtml(t("noticeToStudents"))}</label>
      <button type="button" class="primary" id="notice-send">${escapeHtml(t("noticeAnnounce"))}</button>
    </div>
  `);
  document.getElementById("notice-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => save(groupId)).catch(() => toast(t("error"), "err"));
  });
  document.getElementById("notice-open").addEventListener("click", () => {
    document.getElementById("notice-sheet").hidden = false;
  });
  document.getElementById("notice-send").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => send(groupId)).catch(() => toast(t("error"), "err"));
  });
}

function choices(rows, currentValue) {
  const value = currentValue == null ? "" : String(currentValue);
  return rows
    .map(([id, key]) => {
      const on = id === value ? " selected" : "";
      return `<option value="${id}"${on}>${escapeHtml(t(key))}</option>`;
    })
    .join("");
}

async function save(groupId) {
  const lesson = document.getElementById("notice-lesson").value;
  const fee = document.getElementById("notice-fee").value;
  const chat = document.getElementById("notice-chat").value;
  await api(`/api/tutor/groups/${groupId}/notify`, {
    method: "PUT",
    body: JSON.stringify({
      remind_lesson_min: lesson ? Number(lesson) : null,
      remind_fee_days: fee ? Number(fee) : null,
      fee_in_group: document.getElementById("notice-public").checked,
    }),
  });
  await api(`/api/tutor/groups/${groupId}/chat`, {
    method: "PUT",
    body: JSON.stringify({ chat_id: chat ? Number(chat) : null }),
  });
  haptic("success");
  toast(t("saved"), "ok");
}

async function send(groupId) {
  await api(`/api/tutor/groups/${groupId}/announce`, {
    method: "POST",
    body: JSON.stringify({
      text: document.getElementById("notice-text").value,
      to_chat: document.getElementById("notice-to-chat").checked,
      to_students: document.getElementById("notice-to-students").checked,
    }),
  });
  haptic("success");
  toast(t("noticeSent"), "ok");
  document.getElementById("notice-text").value = "";
}

function hashParts() {
  return (location.hash || "").split("?")[0].replace(/^#\/?/, "").split("/").filter(Boolean);
}
