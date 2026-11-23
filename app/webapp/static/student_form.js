import { api, go, haptic } from "./api.js";
import { showLimit } from "./limits.js";
import { escapeHtml, setHtml, t, toast, withBusy } from "./ui.js";

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
  group: "stuGroupNeed",
};

/** The add and edit form. `saved` receives the list payload; `remove` deletes one card. */
export function paintStudentForm(row, selectedIds, catalog, hooks) {
  const status = row ? row.status : "debtor";
  const chosen = new Set(selectedIds || []);
  const groupChips = catalog.length
    ? catalog
        .map((group) => {
          const on = chosen.has(group.id) ? " selected" : "";
          const when = `${group.start}–${group.end}`;
          return `<button type="button" class="chip-btn${on}" data-group="${group.id}">${escapeHtml(group.name)} · ${escapeHtml(when)}</button>`;
        })
        .join("")
    : "";
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
      <div class="field"><span class="field-label">${escapeHtml(t("stuGroups"))}</span>
        ${catalog.length ? `<div class="chips" id="stu-groups">${groupChips}</div>` : `<p class="stu-meta">${escapeHtml(t("stuNoGroups"))}</p><button type="button" class="primary" id="stu-make-group">${escapeHtml(t("stuMakeGroup"))}</button>`}
      </div>
      ${catalog.length ? `<button type="button" class="primary" id="stu-save">${escapeHtml(t("save"))}</button>` : ""}
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
  document.querySelectorAll("[data-group]").forEach((node) => {
    node.addEventListener("click", () => node.classList.toggle("selected"));
  });
  const maker = document.getElementById("stu-make-group");
  if (maker) maker.addEventListener("click", () => go("cabinet/groups/new"));
  const saveButton = document.getElementById("stu-save");
  if (saveButton) {
    saveButton.addEventListener("click", (event) => {
      withBusy(event.currentTarget, () => save(row, catalog, hooks)).catch(showFormError);
    });
  }
  const remove = document.getElementById("stu-delete");
  if (remove) {
    remove.addEventListener("click", (event) => {
      withBusy(event.currentTarget, () => hooks.remove(row.id)).catch(showFormError);
    });
  }
}

async function save(row, catalog, hooks) {
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
    group_ids: [...document.querySelectorAll("#stu-groups [data-group].selected")].map((node) =>
      Number(node.getAttribute("data-group")),
    ),
  };
  if (catalog.length && !body.group_ids.length) {
    toast(t("stuGroupNeed"), "err");
    return;
  }
  const path = row ? `/api/tutor/students/${row.id}` : "/api/tutor/students";
  const data = await api(path, { method: row ? "PATCH" : "POST", body: JSON.stringify(body) });
  hooks.saved(data);
  haptic("success");
  toast(t("saved"), "ok");
  const nextId = row ? row.id : data.created_id;
  go(nextId ? `cabinet/students/${nextId}` : "cabinet/students");
}

function showFormError(err) {
  if (showLimit(err)) return;
  toast(t(ERROR_KEY[err.code] || "error"), "err");
}
