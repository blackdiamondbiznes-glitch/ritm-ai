import { api, go, haptic, tg } from "./api.js";
import { bindCabinetSwitch, cabinetSwitch, current, escapeHtml, formatNumber, setHtml, showError, skeleton, t, toast, withBusy } from "./ui.js";

const STATUSES = ["paid", "debtor", "inactive"];
const STATUS_KEY = { paid: "stuPaid", debtor: "stuDebtor", inactive: "stuInactive" };
const ERROR_KEY = {
  empty: "stuNameNeed",
  long: "stuNameLong",
  note: "stuNoteLong",
  phone: "stuPhoneBad",
  amount: "stuAmountBad",
  choice: "error",
  missing: "stuMissing",
};

let cache = null;
let filter = "all";

export async function renderStudents(sub, id, seq) {
  const place = studentPlace(sub, id);
  try {
    if (place.mode === "profile") {
      setHtml(skeleton("list"));
      const profile = await api(`/api/tutor/students/${place.id}`);
      if (!current(seq)) return;
      paintProfile(profile);
      return;
    }
    if (!cache || place.mode === "list") {
      setHtml(skeleton("list"));
      cache = await api("/api/tutor/students");
    }
    if (!current(seq)) return;
    if (place.mode === "new") paintForm(null);
    else if (place.mode === "edit") paintEdit(place.id);
    else {
      filter = place.filter;
      paintList();
    }
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function studentPlace(sub, id) {
  const parts = (location.hash || "").replace(/^#\/?/, "").split("/").filter(Boolean);
  const third = parts[2] || "";
  const fourth = parts[3] || "";
  if (sub === "new" || third === "new") return { mode: "new" };
  if (id && fourth === "edit") return { mode: "edit", id };
  if (id) return { mode: "profile", id };
  if (STATUSES.includes(third)) return { mode: "list", filter: third };
  return { mode: "list", filter: "all" };
}

const LESSON_KEY = { scheduled: "lesScheduled", done: "lesDone", cancelled: "lesCancelled" };

function paintProfile(data) {
  const row = data.student;
  const lessons = data.lessons || [];
  const reminders = data.reminders || [];
  const phone = row.phone ? escapeHtml(row.phone) : escapeHtml(t("stuNoPhone"));
  const note = row.note ? `<div class="card"><div class="stu-meta">${escapeHtml(row.note)}</div></div>` : "";
  const lessonBody = lessons.length
    ? lessons.map(lessonRow).join("")
    : `<div class="stu-meta">${escapeHtml(t("stuNoLessons"))}</div>`;
  const reminderBody = reminders.length
    ? reminders.map(reminderRow).join("")
    : `<div class="stu-meta">${escapeHtml(t("stuNoReminders"))}</div>`;
  setHtml(`
    <div class="header">
      <h1>${escapeHtml(row.name)}</h1>
      <p>${escapeHtml(t(STATUS_KEY[row.status] || "stuMissing"))}</p>
    </div>
    <div class="card">
      <div class="stu-meta">${phone}</div>
      <div class="big">${escapeHtml(t("stuSum", { n: formatNumber(row.amount_uzs) }))}</div>
    </div>
    ${note}
    <div class="card">
      <div class="card-title">${escapeHtml(t("stuLessons"))}</div>
      ${lessonBody}
      <button type="button" class="primary" id="stu-lesson">${escapeHtml(t("lesAdd"))}</button>
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("stuReminders"))}</div>
      ${reminderBody}
    </div>
    <button type="button" class="primary" id="stu-edit">${escapeHtml(t("stuEdit"))}</button>
    <button type="button" class="ghost danger" id="stu-delete">${escapeHtml(t("stuDelete"))}</button>
  `);
  document.querySelectorAll("[data-lesson]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(`cabinet/lessons/${node.getAttribute("data-lesson")}`);
    });
  });
  document.getElementById("stu-lesson").addEventListener("click", () => {
    haptic("light");
    go(`cabinet/lessons/new/${row.id}`);
  });
  document.getElementById("stu-edit").addEventListener("click", () => {
    haptic("light");
    go(`cabinet/students/${row.id}/edit`);
  });
  document.getElementById("stu-delete").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => destroy(row.id)).catch((err) => toast(t(ERROR_KEY[err.code] || "error"), "err"));
  });
}

function lessonRow(row) {
  const when = row.starts_at ? ` · ${escapeHtml(formatWhen(row.starts_at))}` : "";
  return `<button type="button" class="list-btn" data-lesson="${row.id}">
    <div class="stu-row">
      <div class="chat-name">${escapeHtml(row.title)}</div>
      <span class="stu-badge les-${row.status}">${escapeHtml(t(LESSON_KEY[row.status] || "lesScheduled"))}</span>
    </div>
    <div class="stu-meta">${escapeHtml(t("stuSum", { n: formatNumber(row.amount_uzs) }))}${when}</div>
  </button>`;
}

function reminderRow(row) {
  const state = row.sent ? t("remSent") : t("remWaiting");
  return `<div class="stu-meta">${escapeHtml(row.text)} · ${escapeHtml(formatWhen(row.send_at))} · ${escapeHtml(state)}</div>`;
}

function formatWhen(iso) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Tashkent",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const pick = (type) => parts.find((part) => part.type === type).value;
  return `${pick("day")}.${pick("month")} ${pick("hour")}:${pick("minute")}`;
}

function paintEdit(id) {
  const row = (cache.students || []).find((item) => item.id === id);
  if (!row) {
    setHtml(`<div class="card err">${escapeHtml(t("stuMissing"))}</div>`);
    return;
  }
  paintForm(row);
}

function paintList() {
  const counts = cache.counts || { paid: 0, debtor: 0, inactive: 0 };
  const rows = (cache.students || []).filter((item) => filter === "all" || item.status === filter);
  const chips = ["all", ...STATUSES]
    .map((status) => {
      const label = status === "all" ? t("stuAll") : t(STATUS_KEY[status]);
      const on = status === filter ? " selected" : "";
      return `<button type="button" class="chip-btn${on}" data-filter="${status}">${escapeHtml(label)}</button>`;
    })
    .join("");
  const body = rows.length
    ? rows.map(rowButton).join("")
    : `<div class="card muted">${escapeHtml(t((cache.students || []).length ? "stuFilterEmpty" : "stuEmpty"))}</div>`;
  setHtml(`
    ${cabinetSwitch("students")}
    <div class="header"><h1>${escapeHtml(t("stuTitle"))}</h1><p>${escapeHtml(t("stuLead"))}</p></div>
    <div class="kpis">
      ${kpi(counts.paid, "stuPaid")}
      ${kpi(counts.debtor, "stuDebtor")}
      ${kpi(counts.inactive, "stuInactive")}
    </div>
    <div class="chips chips-scroll">${chips}</div>
    ${body}
    <button type="button" class="primary" id="stu-add">${escapeHtml(t("stuAdd"))}</button>
  `);
  bindCabinetSwitch();
  document.querySelectorAll("[data-filter]").forEach((node) => {
    node.addEventListener("click", () => {
      filter = node.getAttribute("data-filter");
      haptic("light");
      paintList();
    });
  });
  document.querySelectorAll("[data-student]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(`cabinet/students/${node.getAttribute("data-student")}`);
    });
  });
  document.getElementById("stu-add").addEventListener("click", () => {
    haptic("light");
    go("cabinet/students/new");
  });
}

function paintForm(row) {
  const status = row ? row.status : "debtor";
  const chips = STATUSES.map((item) => {
    const on = item === status ? " selected" : "";
    return `<button type="button" class="chip-btn${on}" data-status="${item}">${escapeHtml(t(STATUS_KEY[item]))}</button>`;
  }).join("");
  setHtml(`
    <div class="header"><h1>${escapeHtml(t(row ? "stuEdit" : "stuAdd"))}</h1></div>
    <div class="card">
      <label class="field"><span class="field-label">${escapeHtml(t("stuName"))}</span>
        <input class="input" id="stu-name" maxlength="80" value="${escapeHtml(row ? row.name : "")}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("stuPhone"))}</span>
        <input class="input" id="stu-phone" maxlength="20" inputmode="tel" value="${escapeHtml(row ? row.phone || "" : "")}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("stuAmount"))}</span>
        <input class="input" id="stu-amount" inputmode="numeric" value="${row ? row.amount_uzs : 0}"></label>
      <label class="field"><span class="field-label">${escapeHtml(t("stuNote"))}</span>
        <textarea class="input" id="stu-note" maxlength="300" rows="3">${escapeHtml(row ? row.note || "" : "")}</textarea></label>
      <div class="field"><span class="field-label">${escapeHtml(t("stuStatus"))}</span>
        <div class="chips" id="stu-status" data-value="${status}">${chips}</div></div>
      <button type="button" class="primary" id="stu-save">${escapeHtml(t("save"))}</button>
      ${row ? `<button type="button" class="ghost danger" id="stu-delete">${escapeHtml(t("stuDelete"))}</button>` : ""}
    </div>
  `);
  document.querySelectorAll("[data-status]").forEach((node) => {
    node.addEventListener("click", () => {
      const box = document.getElementById("stu-status");
      box.setAttribute("data-value", node.getAttribute("data-status"));
      box.querySelectorAll("[data-status]").forEach((chip) => {
        chip.classList.toggle("selected", chip === node);
      });
    });
  });
  document.getElementById("stu-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => save(row)).catch((err) => toast(t(ERROR_KEY[err.code] || "error"), "err"));
  });
  const remove = document.getElementById("stu-delete");
  if (remove) {
    remove.addEventListener("click", (event) => {
      withBusy(event.currentTarget, () => destroy(row.id)).catch((err) => toast(t(ERROR_KEY[err.code] || "error"), "err"));
    });
  }
}

async function save(row) {
  const amountRaw = document.getElementById("stu-amount").value.trim();
  const amount = amountRaw === "" ? 0 : Number(amountRaw);
  if (!Number.isInteger(amount)) {
    toast(t("stuAmountBad"), "err");
    return;
  }
  const body = {
    name: document.getElementById("stu-name").value,
    phone: document.getElementById("stu-phone").value,
    amount_uzs: amount,
    note: document.getElementById("stu-note").value,
    status: document.getElementById("stu-status").getAttribute("data-value"),
  };
  const path = row ? `/api/tutor/students/${row.id}` : "/api/tutor/students";
  cache = await api(path, { method: row ? "PATCH" : "POST", body: JSON.stringify(body) });
  haptic("success");
  toast(t("saved"), "ok");
  const nextId = row ? row.id : cache.created_id;
  go(nextId ? `cabinet/students/${nextId}` : "cabinet/students");
}

async function destroy(id) {
  const yes = await ask(t("stuDeleteAsk"));
  if (!yes) return;
  cache = await api(`/api/tutor/students/${id}`, { method: "DELETE" });
  haptic("success");
  toast(t("saved"), "ok");
  go("cabinet/students");
}

function ask(text) {
  if (tg && tg.showConfirm) return new Promise((resolve) => tg.showConfirm(text, resolve));
  return Promise.resolve(window.confirm(text));
}

function rowButton(row) {
  const phone = row.phone ? ` · ${row.phone}` : "";
  const note = row.note ? `<div class="stu-meta">${escapeHtml(row.note)}</div>` : "";
  return `<button type="button" class="card list-btn" data-student="${row.id}">
    <div class="stu-row">
      <div class="chat-name">${escapeHtml(row.name)}</div>
      <span class="stu-badge stu-${row.status}">${escapeHtml(t(STATUS_KEY[row.status]))}</span>
    </div>
    <div class="stu-meta">${escapeHtml(t("stuSum", { n: formatNumber(row.amount_uzs) }))}${escapeHtml(phone)}</div>
    ${note}
  </button>`;
}

function kpi(value, key) {
  return `<div class="kpi"><div class="kpi-value">${escapeHtml(formatNumber(value))}</div>
    <div class="kpi-label">${escapeHtml(t(key))}</div></div>`;
}
