import { announce, announceBlock } from "./announce.js";
import { api, go, haptic, tg } from "./api.js";
import { showLimit } from "./limits.js";
import { mountRequests } from "./requests.js";
import {
  bindCabinetSwitch,
  cabinetSwitch,
  current,
  escapeHtml,
  setHtml,
  showError,
  skeleton,
  t,
  toast,
  withBusy,
} from "./ui.js";

const DAYS = [1, 2, 3, 4, 5, 6, 7];
const ERROR_KEY = {
  empty: "grpNameNeed",
  long: "grpNameLong",
  days: "grpDaysNeed",
  time: "grpTimeBad",
  student: "lesStudentBad",
  missing: "grpMissing",
  send: "grpSendBad",
  date: "lesWhenBad",
  score: "topScoreBad",
};

let cache = null;
let board = null;

export async function renderGroups(seq) {
  const place = groupPlace();
  try {
    if (place.mode === "topic-new") {
      setHtml(skeleton("list"));
      cache = await api(`/api/tutor/groups/${place.id}`);
    } else if (place.mode === "topic") {
      setHtml(skeleton("list"));
      cache = await api(`/api/tutor/groups/${place.id}/topics/${place.topicId}`);
    } else if (place.mode === "open" || place.mode === "edit") {
      setHtml(skeleton("list"));
      const detail = await api(`/api/tutor/groups/${place.id}`);
      board = place.mode === "open" ? await api(`/api/tutor/groups/${place.id}/board`) : null;
      cache = detail;
    } else if (!cache || place.mode === "list") {
      setHtml(skeleton("list"));
      cache = await api("/api/tutor/groups");
    }
    if (!current(seq)) return;
    if (place.mode === "new") paintForm(null);
    else if (place.mode === "edit") paintForm(cache.group);
    else if (place.mode === "topic-new") paintTopicForm(place.id);
    else if (place.mode === "topic") paintMarks(place.id);
    else if (place.mode === "open") paintOpen();
    else paintList();
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function groupPlace() {
  const parts = (location.hash || "").replace(/^#\/?/, "").split("/").filter(Boolean);
  const third = parts[2] || "";
  const fourth = parts[3] || "";
  const fifth = parts[4] || "";
  if (third === "new") return { mode: "new" };
  if (/^\d+$/.test(third) && fourth === "edit") return { mode: "edit", id: Number(third) };
  if (/^\d+$/.test(third) && fourth === "topic" && fifth === "new") {
    return { mode: "topic-new", id: Number(third) };
  }
  if (/^\d+$/.test(third) && fourth === "topic" && /^\d+$/.test(fifth)) {
    return { mode: "topic", id: Number(third), topicId: Number(fifth) };
  }
  if (/^\d+$/.test(third)) return { mode: "open", id: Number(third) };
  return { mode: "list" };
}

function paintList() {
  const rows = cache.groups || [];
  const body = rows.length
    ? rows.map(groupButton).join("")
    : `<div class="card muted">${escapeHtml(t("grpEmpty"))}</div>`;
  setHtml(`
    ${cabinetSwitch("groups")}
    <div class="header"><h1>${escapeHtml(t("grpTitle"))}</h1><p>${escapeHtml(t("grpLead"))}</p></div>
    <div class="card" id="req-root"></div>
    ${body}
    <button type="button" class="primary" id="grp-add">${escapeHtml(t("grpAdd"))}</button>
  `);
  bindCabinetSwitch();
  mountRequests(async () => {
    cache = await api("/api/tutor/groups");
    paintList();
  }).catch(() => {});
  document.querySelectorAll("[data-group]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(`cabinet/groups/${node.getAttribute("data-group")}`);
    });
  });
  document.getElementById("grp-add").addEventListener("click", () => {
    haptic("light");
    go("cabinet/groups/new");
  });
}

function paintOpen() {
  const group = cache.group;
  const members = cache.members || [];
  const available = cache.available || [];
  const people = members.length
    ? members
        .map(
          (item) => `<div class="stu-row">
            <button type="button" class="list-btn" data-student="${item.id}">${escapeHtml(item.name)}</button>
            <button type="button" class="ghost" data-out="${item.id}">${escapeHtml(t("grpOut"))}</button>
          </div>`,
        )
        .join("")
    : `<div class="stu-meta">${escapeHtml(t("grpNone"))}</div>`;
  const options = [`<option value="">${escapeHtml(t("grpPick"))}</option>`]
    .concat(available.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`))
    .join("");
  setHtml(`
    <div class="header">
      <h1>${escapeHtml(group.name)}</h1>
      <p>${escapeHtml(schedule(group))}</p>
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("bookTitle"))}</div>
      ${gradebookTable(board)}
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("rankTitle"))}</div>
      ${rankRows((board && board.ranking) || [])}
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("topTopics"))}</div>
      ${topicRows((board && board.topics) || [])}
      <button type="button" class="primary" id="top-add">${escapeHtml(t("topAdd"))}</button>
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("grpStudents"))}</div>
      ${people}
      <label class="field"><span class="field-label">${escapeHtml(t("grpAddStudent"))}</span>
        <select class="input" id="grp-pick">${options}</select></label>
      <button type="button" class="primary" id="grp-in">${escapeHtml(t("grpAddStudent"))}</button>
    </div>
    ${announceBlock()}
    <button type="button" class="primary" id="grp-edit">${escapeHtml(t("grpEdit"))}</button>
    <button type="button" class="ghost danger" id="grp-delete">${escapeHtml(t("stuDelete"))}</button>
  `);
  document.querySelectorAll("[data-student]").forEach((node) => {
    node.addEventListener("click", () => go(`cabinet/students/${node.getAttribute("data-student")}`));
  });
  document.querySelectorAll("[data-out]").forEach((node) => {
    node.addEventListener("click", (event) => {
      withBusy(event.currentTarget, () => drop(group.id, Number(node.getAttribute("data-out")))).catch(showFormError);
    });
  });
  document.getElementById("grp-in").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => admit(group.id)).catch(showFormError);
  });
  document.querySelectorAll("[data-topic]").forEach((node) => {
    node.addEventListener("click", () => go(`cabinet/groups/${group.id}/topic/${node.getAttribute("data-topic")}`));
  });
  document.getElementById("top-add").addEventListener("click", () => go(`cabinet/groups/${group.id}/topic/new`));
  const send = document.getElementById("grp-send");
  if (send) {
    send.addEventListener("click", (event) => {
      withBusy(event.currentTarget, () => announce(group.id)).catch(showFormError);
    });
  }
  const connect = document.getElementById("grp-connect");
  if (connect) connect.addEventListener("click", () => go("profile/connect"));
  document.getElementById("grp-edit").addEventListener("click", () => go(`cabinet/groups/${group.id}/edit`));
  document.getElementById("grp-delete").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => destroy(group.id)).catch(showFormError);
  });
}

function paintForm(group) {
  const chosen = new Set(group ? group.weekdays : [1, 3, 5]);
  const chips = DAYS.map((day) => {
    const on = chosen.has(day) ? " selected" : "";
    return `<button type="button" class="chip-btn${on}" data-day="${day}">${escapeHtml(t(`day${day}`))}</button>`;
  }).join("");
  setHtml(`
    <div class="header"><h1>${escapeHtml(t(group ? "grpEdit" : "grpAdd"))}</h1></div>
    <div class="card">
      <label class="field"><span class="field-label">${escapeHtml(t("grpName"))}</span>
        <input class="input" id="grp-name" maxlength="80" value="${escapeHtml(group ? group.name : "")}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("grpLevel"))}</span>
        <input class="input" id="grp-level" maxlength="40" value="${escapeHtml(group ? group.level || "" : "")}"></label>
      <div class="field"><span class="field-label">${escapeHtml(t("grpDays"))}</span>
        <div class="chips" id="grp-days">${chips}</div></div>
      <label class="field"><span class="field-label">${escapeHtml(t("grpStart"))}</span>
        <input class="input" id="grp-start" type="time" value="${group ? group.start : "08:00"}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("grpEnd"))}</span>
        <input class="input" id="grp-end" type="time" value="${group ? group.end : "10:00"}"></label>
      <button type="button" class="primary" id="grp-save">${escapeHtml(t("save"))}</button>
    </div>
  `);
  document.querySelectorAll("[data-day]").forEach((node) => {
    node.addEventListener("click", () => node.classList.toggle("selected"));
  });
  document.getElementById("grp-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => save(group)).catch(showFormError);
  });
}

async function save(group) {
  const weekdays = [...document.querySelectorAll("[data-day].selected")].map((node) =>
    Number(node.getAttribute("data-day")),
  );
  const body = {
    name: document.getElementById("grp-name").value,
    level: document.getElementById("grp-level").value,
    weekdays,
    start: document.getElementById("grp-start").value,
    end: document.getElementById("grp-end").value,
  };
  const path = group ? `/api/tutor/groups/${group.id}` : "/api/tutor/groups";
  const data = await api(path, { method: group ? "PATCH" : "POST", body: JSON.stringify(body) });
  haptic("success");
  toast(t("saved"), "ok");
  const next = group ? group.id : data.created_id;
  go(next ? `cabinet/groups/${next}` : "cabinet/groups");
}

async function admit(groupId) {
  const studentId = Number(document.getElementById("grp-pick").value);
  if (!studentId) {
    toast(t("grpPick"), "err");
    return;
  }
  cache = await api(`/api/tutor/groups/${groupId}/students`, {
    method: "POST",
    body: JSON.stringify({ student_id: studentId }),
  });
  haptic("success");
  paintOpen();
}

async function drop(groupId, studentId) {
  cache = await api(`/api/tutor/groups/${groupId}/students/${studentId}`, { method: "DELETE" });
  haptic("success");
  paintOpen();
}

async function destroy(id) {
  const yes = await ask(t("grpDeleteAsk"));
  if (!yes) return;
  cache = await api(`/api/tutor/groups/${id}`, { method: "DELETE" });
  haptic("success");
  go("cabinet/groups");
}

function ask(text) {
  if (tg && tg.showConfirm) return new Promise((resolve) => tg.showConfirm(text, resolve));
  return Promise.resolve(window.confirm(text));
}

function showFormError(err) {
  if (showLimit(err)) return;
  toast(t(ERROR_KEY[err.code] || "error"), "err");
}

function paintTopicForm(groupId) {
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Tashkent" }).format(new Date());
  setHtml(`
    <div class="header"><h1>${escapeHtml(t("topAdd"))}</h1></div>
    <div class="card">
      <label class="field"><span class="field-label">${escapeHtml(t("topTopic"))}</span>
        <input class="input" id="top-title" maxlength="120"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("topDate"))}</span>
        <input class="input" id="top-date" type="date" value="${today}"></label>
      <button type="button" class="primary" id="top-save">${escapeHtml(t("save"))}</button>
    </div>
  `);
  document.getElementById("top-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => createTopic(groupId)).catch((err) => {
      toast(t(err.code === "empty" ? "topNameNeed" : ERROR_KEY[err.code] || "error"), "err");
    });
  });
}

function paintMarks(groupId) {
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
  await api(`/api/tutor/groups/${groupId}/topics/${topicId}`, {
    method: "PUT",
    body: JSON.stringify({ scores }),
  });
  haptic("success");
  toast(t("saved"), "ok");
  go(`cabinet/groups/${groupId}`);
}

function gradebookTable(data) {
  const topics = (data && data.topics) || [];
  const rows = (data && data.gradebook) || [];
  if (!topics.length || !rows.length) return `<div class="stu-meta">${escapeHtml(t("bookEmpty"))}</div>`;
  const head = topics
    .map((topic) => `<th>${escapeHtml(topic.title)}</th>`)
    .join("");
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

function rankRows(rows) {
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

function topicRows(rows) {
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

function groupButton(group) {
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
  const level = group.level ? ` · ${group.level}` : "";
  return `${days} · ${group.start}–${group.end}${level}`;
}
