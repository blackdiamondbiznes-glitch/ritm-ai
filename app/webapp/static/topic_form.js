import { api, go, haptic } from "./api.js";
import { showLimit } from "./limits.js";
import { escapeHtml, setHtml, t, toast, withBusy } from "./ui.js";

const ERROR_KEY = { empty: "topNameNeed", long: "topNameLong", date: "lesWhenBad", score: "topScoreBad" };

export function paintTopicForm(groupId) {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tashkent" }).format(new Date());
  setHtml(`
    <div class="header"><h1>${escapeHtml(t("topAdd"))}</h1></div>
    <div class="card">
      <label class="field"><span class="field-label">${escapeHtml(t("topTopic"))}</span>
        <input class="input" id="top-title" maxlength="120"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("topDate"))}</span>
        <input class="input" id="top-date" type="date" value="${today}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("hwText"))}</span>
        <textarea class="input" id="top-homework" maxlength="1000"></textarea></label>
      <label class="field"><span class="field-label">${escapeHtml(t("hwDue"))}</span>
        <input class="input" id="top-due" type="date"></label>
      <button type="button" class="primary" id="top-save">${escapeHtml(t("save"))}</button>
    </div>
  `);
  document.getElementById("top-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => createTopic(groupId)).catch(showFormError);
  });
}

export function paintMarks(groupId, cache) {
  const topic = cache.topic;
  const marks = cache.marks || [];
  const rows = marks
    .map(
      (item) => `<label class="field"><span class="field-label">${escapeHtml(item.name)}</span>
        <input class="input" data-mark="${item.student_id}" inputmode="numeric" maxlength="2" value="${item.score === null || item.score === undefined ? "" : item.score}"></label>`,
    )
    .join("");
  setHtml(`
    <div class="header"><h1>${escapeHtml(topic.title)}</h1><p>${escapeHtml(topic.held_on)}</p></div>
    <div class="card">
      <label class="field"><span class="field-label">${escapeHtml(t("hwText"))}</span>
        <textarea class="input" id="top-homework" maxlength="1000">${escapeHtml(topic.homework || "")}</textarea></label>
      <label class="field"><span class="field-label">${escapeHtml(t("hwDue"))}</span>
        <input class="input" id="top-due" type="date" value="${escapeHtml(topic.homework_due || "")}"></label>
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("topScore"))}</div>
      ${rows || `<div class="stu-meta">${escapeHtml(t("grpNone"))}</div>`}
      <button type="button" class="primary" id="mark-save">${escapeHtml(t("save"))}</button>
    </div>
  `);
  document.getElementById("mark-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => saveMarks(groupId, topic.id)).catch(showFormError);
  });
}

async function createTopic(groupId) {
  const data = await api(`/api/tutor/groups/${groupId}/topics`, {
    method: "POST",
    body: JSON.stringify({
      title: document.getElementById("top-title").value,
      held_on: document.getElementById("top-date").value,
      homework: document.getElementById("top-homework").value,
      homework_due: document.getElementById("top-due").value,
    }),
  });
  haptic("success");
  go(`cabinet/groups/${groupId}/topic/${data.topic.id}`);
}

async function saveMarks(groupId, topicId) {
  const scores = [...document.querySelectorAll("[data-mark]")].map((node) => {
    const raw = node.value.trim();
    return { student_id: Number(node.getAttribute("data-mark")), score: raw === "" ? null : Number(raw) };
  });
  if (scores.some((item) => item.score !== null && !Number.isInteger(item.score))) {
    toast(t("topScoreBad"), "err");
    return;
  }
  await api(`/api/tutor/groups/${groupId}/topics/${topicId}/homework`, {
    method: "PUT",
    body: JSON.stringify({
      homework: document.getElementById("top-homework").value,
      homework_due: document.getElementById("top-due").value,
    }),
  });
  await api(`/api/tutor/groups/${groupId}/topics/${topicId}`, {
    method: "PUT",
    body: JSON.stringify({ scores }),
  });
  haptic("success");
  toast(t("saved"), "ok");
  go(`cabinet/groups/${groupId}`);
}

function showFormError(err) {
  if (showLimit(err)) return;
  toast(t(ERROR_KEY[err.code] || "error"), "err");
}
