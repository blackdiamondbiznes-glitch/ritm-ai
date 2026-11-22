import { api, go, haptic, tg } from "./api.js";
import {
  bindCabinetSwitch,
  cabinetSwitch,
  current,
  escapeHtml,
  formatNumber,
  setHtml,
  showError,
  skeleton,
  t,
  toast,
  withBusy,
} from "./ui.js";

const STATUSES = ["scheduled", "done", "cancelled"];
const STATUS_KEY = { scheduled: "lesScheduled", done: "lesDone", cancelled: "lesCancelled" };
const ERROR_KEY = {
  empty: "lesNameNeed",
  long: "lesNameLong",
  note: "stuNoteLong",
  amount: "stuAmountBad",
  choice: "error",
  when: "lesWhenBad",
  student: "lesStudentBad",
  missing: "lesMissing",
};

let cache = null;
let filter = "all";

export async function renderLessons(seq) {
  const place = lessonPlace();
  try {
    if (!cache || place.mode === "list") {
      setHtml(skeleton("list"));
      cache = await api("/api/tutor/lessons");
    }
    if (!current(seq)) return;
    if (place.mode === "new") paintForm(null, place.studentId);
    else if (place.mode === "edit") paintEdit(place.id);
    else {
      filter = place.filter;
      paintList();
    }
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function lessonPlace() {
  const parts = (location.hash || "").replace(/^#\/?/, "").split("/").filter(Boolean);
  const third = parts[2] || "";
  if (third === "new") {
    const picked = parts[3] || "";
    return { mode: "new", studentId: /^\d+$/.test(picked) ? Number(picked) : null };
  }
  if (/^\d+$/.test(third)) return { mode: "edit", id: Number(third) };
  if (STATUSES.includes(third)) return { mode: "list", filter: third };
  return { mode: "list", filter: "all" };
}

function paintEdit(id) {
  const row = (cache.lessons || []).find((item) => item.id === id);
  if (!row) {
    setHtml(`<div class="card err">${escapeHtml(t("lesMissing"))}</div>`);
    return;
  }
  paintForm(row);
}

function paintList() {
  const counts = cache.counts || { scheduled: 0, done: 0, cancelled: 0 };
  const rows = (cache.lessons || []).filter((item) => filter === "all" || item.status === filter);
  const chips = ["all", ...STATUSES]
    .map((status) => {
      const label = status === "all" ? t("stuAll") : t(STATUS_KEY[status]);
      const on = status === filter ? " selected" : "";
      return `<button type="button" class="chip-btn${on}" data-filter="${status}">${escapeHtml(label)}</button>`;
    })
    .join("");
  const emptyKey = (cache.lessons || []).length ? "lesFilterEmpty" : "lesEmpty";
  const body = rows.length
    ? rows.map(rowButton).join("")
    : `<div class="card muted">${escapeHtml(t(emptyKey))}</div>`;
  setHtml(`
    ${cabinetSwitch("lessons")}
    <div class="header"><h1>${escapeHtml(t("lesTitle"))}</h1><p>${escapeHtml(t("lesLead"))}</p></div>
    <div class="kpis">
      ${kpi(counts.scheduled, "lesScheduled")}
      ${kpi(counts.done, "lesDone")}
      ${kpi(counts.cancelled, "lesCancelled")}
    </div>
    <div class="chips chips-scroll">${chips}</div>
    ${body}
    <button type="button" class="primary" id="les-add">${escapeHtml(t("lesAdd"))}</button>
  `);
  bindCabinetSwitch();
  document.querySelectorAll("[data-filter]").forEach((node) => {
    node.addEventListener("click", () => {
      filter = node.getAttribute("data-filter");
      haptic("light");
      paintList();
    });
  });
  document.querySelectorAll("[data-lesson]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(`cabinet/lessons/${node.getAttribute("data-lesson")}`);
    });
  });
  document.getElementById("les-add").addEventListener("click", () => {
    haptic("light");
    go("cabinet/lessons/new");
  });
}

function paintForm(row, presetStudent) {
  const status = row ? row.status : "scheduled";
  const chips = STATUSES.map((item) => {
    const on = item === status ? " selected" : "";
    return `<button type="button" class="chip-btn${on}" data-status="${item}">${escapeHtml(t(STATUS_KEY[item]))}</button>`;
  }).join("");
  const selected = row && row.student_id ? String(row.student_id) : presetStudent ? String(presetStudent) : "";
  const options = [`<option value="">${escapeHtml(t("lesNoStudent"))}</option>`]
    .concat(
      (cache.students || []).map((student) => {
        const on = String(student.id) === selected ? " selected" : "";
        return `<option value="${student.id}"${on}>${escapeHtml(student.name)}</option>`;
      }),
    )
    .join("");
  setHtml(`
    <div class="header"><h1>${escapeHtml(t(row ? "lesEdit" : "lesAdd"))}</h1></div>
    <div class="card">
      <label class="field"><span class="field-label">${escapeHtml(t("lesName"))}</span>
        <input class="input" id="les-title" maxlength="120" value="${escapeHtml(row ? row.title : "")}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("lesStudent"))}</span>
        <select class="input" id="les-student">${options}</select></label>
      <label class="field"><span class="field-label">${escapeHtml(t("lesWhen"))}</span>
        <input class="input" id="les-when" type="datetime-local" value="${escapeHtml(whenValue(row && row.starts_at))}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("stuAmount"))}</span>
        <input class="input" id="les-amount" inputmode="numeric" value="${row ? row.amount_uzs : 0}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("stuNote"))}</span>
        <textarea class="input" id="les-note" maxlength="300" rows="3">${escapeHtml(row ? row.note || "" : "")}</textarea></label>
      <div class="field"><span class="field-label">${escapeHtml(t("stuStatus"))}</span>
        <div class="chips" id="les-status" data-value="${status}">${chips}</div></div>
      <button type="button" class="primary" id="les-save">${escapeHtml(t("save"))}</button>
      ${row ? `<button type="button" class="ghost danger" id="les-delete">${escapeHtml(t("stuDelete"))}</button>` : ""}
    </div>
  `);
  document.querySelectorAll("[data-status]").forEach((node) => {
    node.addEventListener("click", () => {
      const box = document.getElementById("les-status");
      box.setAttribute("data-value", node.getAttribute("data-status"));
      box.querySelectorAll("[data-status]").forEach((chip) => {
        chip.classList.toggle("selected", chip === node);
      });
    });
  });
  document.getElementById("les-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => save(row)).catch((err) => toast(t(ERROR_KEY[err.code] || "error"), "err"));
  });
  const remove = document.getElementById("les-delete");
  if (remove) {
    remove.addEventListener("click", (event) => {
      withBusy(event.currentTarget, () => destroy(row.id)).catch((err) => toast(t(ERROR_KEY[err.code] || "error"), "err"));
    });
  }
}

async function save(row) {
  const amountRaw = document.getElementById("les-amount").value.trim();
  const amount = amountRaw === "" ? 0 : Number(amountRaw);
  if (!Number.isInteger(amount)) {
    toast(t("stuAmountBad"), "err");
    return;
  }
  const studentRaw = document.getElementById("les-student").value;
  const body = {
    title: document.getElementById("les-title").value,
    student_id: studentRaw ? Number(studentRaw) : null,
    starts_at: document.getElementById("les-when").value,
    amount_uzs: amount,
    note: document.getElementById("les-note").value,
    status: document.getElementById("les-status").getAttribute("data-value"),
  };
  const path = row ? `/api/tutor/lessons/${row.id}` : "/api/tutor/lessons";
  cache = await api(path, { method: row ? "PATCH" : "POST", body: JSON.stringify(body) });
  haptic("success");
  toast(t("saved"), "ok");
  go("cabinet/lessons");
}

async function destroy(id) {
  const yes = await ask(t("lesDeleteAsk"));
  if (!yes) return;
  cache = await api(`/api/tutor/lessons/${id}`, { method: "DELETE" });
  haptic("success");
  toast(t("saved"), "ok");
  go("cabinet/lessons");
}

function ask(text) {
  if (tg && tg.showConfirm) return new Promise((resolve) => tg.showConfirm(text, resolve));
  return Promise.resolve(window.confirm(text));
}

function rowButton(row) {
  const who = row.student_name ? escapeHtml(row.student_name) : escapeHtml(t("lesNoStudent"));
  const when = row.starts_at ? ` · ${escapeHtml(formatWhen(row.starts_at))}` : "";
  const note = row.note ? `<div class="stu-meta">${escapeHtml(row.note)}</div>` : "";
  return `<button type="button" class="card list-btn" data-lesson="${row.id}">
    <div class="stu-row">
      <div class="chat-name">${escapeHtml(row.title)}</div>
      <span class="stu-badge les-${row.status}">${escapeHtml(t(STATUS_KEY[row.status]))}</span>
    </div>
    <div class="stu-meta">${who}${when} · ${escapeHtml(t("stuSum", { n: formatNumber(row.amount_uzs) }))}</div>
    ${note}
  </button>`;
}

function kpi(value, key) {
  return `<div class="kpi"><div class="kpi-value">${escapeHtml(formatNumber(value))}</div>
    <div class="kpi-label">${escapeHtml(t(key))}</div></div>`;
}

function whenParts(iso) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Tashkent",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
}

function whenValue(iso) {
  if (!iso) return "";
  const parts = whenParts(iso);
  const pick = (type) => parts.find((part) => part.type === type).value;
  return `${pick("year")}-${pick("month")}-${pick("day")}T${pick("hour")}:${pick("minute")}`;
}

function formatWhen(iso) {
  const parts = whenParts(iso);
  const pick = (type) => parts.find((part) => part.type === type).value;
  return `${pick("day")}.${pick("month")} ${pick("hour")}:${pick("minute")}`;
}
