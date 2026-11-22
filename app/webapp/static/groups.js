import { api, go, haptic, tg } from "./api.js";
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
};

let cache = null;

export async function renderGroups(seq) {
  const place = groupPlace();
  try {
    if (place.mode === "open" || place.mode === "edit") {
      setHtml(skeleton("list"));
      cache = await api(`/api/tutor/groups/${place.id}`);
    } else if (!cache || place.mode === "list") {
      setHtml(skeleton("list"));
      cache = await api("/api/tutor/groups");
    }
    if (!current(seq)) return;
    if (place.mode === "new") paintForm(null);
    else if (place.mode === "edit") paintForm(cache.group);
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
  if (third === "new") return { mode: "new" };
  if (/^\d+$/.test(third) && fourth === "edit") return { mode: "edit", id: Number(third) };
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
    ${body}
    <button type="button" class="primary" id="grp-add">${escapeHtml(t("grpAdd"))}</button>
  `);
  bindCabinetSwitch();
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
      <div class="card-title">${escapeHtml(t("grpStudents"))}</div>
      ${people}
      <label class="field"><span class="field-label">${escapeHtml(t("grpAddStudent"))}</span>
        <select class="input" id="grp-pick">${options}</select></label>
      <button type="button" class="primary" id="grp-in">${escapeHtml(t("grpAddStudent"))}</button>
    </div>
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
  toast(t(ERROR_KEY[err.code] || "error"), "err");
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
