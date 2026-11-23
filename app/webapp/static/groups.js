import { announce, announceBlock } from "./announce.js";
import { groupTabs } from "./group_tabs.js";
import { api, go, haptic, tg } from "./api.js";
import { gradebookTable, groupButton, rankRows, topicRows } from "./group_rows.js";
import { showLimit } from "./limits.js";
import { paintMarks, paintTopicForm } from "./topic_form.js";
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
    else if (place.mode === "topic") paintMarks(place.id, cache);
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
    ${groupTabs(group, "home")}
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
