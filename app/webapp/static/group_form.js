import { api, go, haptic } from "./api.js";
import { showLimit } from "./limits.js";
import { escapeHtml, setHtml, t, toast, withBusy } from "./ui.js";

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

/** Create or edit one group. The same fields as the previous inline form. */
export function paintGroupForm(group) {
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

export function showFormError(err) {
  if (showLimit(err)) return;
  toast(t(ERROR_KEY[err.code] || "error"), "err");
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
