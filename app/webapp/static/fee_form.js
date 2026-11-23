import { api, haptic } from "./api.js";
import { groupTabs } from "./group_tabs.js";
import { current, escapeHtml, setHtml, showError, skeleton, t, toast, withBusy } from "./ui.js";

const MODES = [
  ["none", "feeNone"],
  ["monthly", "feeMonthly"],
  ["package", "feePackage"],
];

export async function renderFeeForm(seq) {
  const groupId = Number(hashParts()[2]);
  setHtml(skeleton("list"));
  try {
    const data = await api(`/api/tutor/groups/${groupId}`);
    if (!current(seq)) return;
    paint(data.group, groupId);
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function paint(group, groupId) {
  const mode = group.fee_mode || "none";
  const chips = MODES.map(([id, key]) => {
    const on = id === mode ? " selected" : "";
    return `<button type="button" class="chip-btn${on}" data-mode="${id}">${escapeHtml(t(key))}</button>`;
  }).join("");
  setHtml(`
    ${groupTabs(group, "fee")}
    <div class="card">
      <div class="chips" id="fee-mode">${chips}</div>
      <label class="field"><span class="field-label">${escapeHtml(t("feeAmount"))}</span>
        <input class="input" id="fee-amount" inputmode="numeric" value="${group.fee_uzs || 0}"></label>
      <label class="field" id="fee-day-row"><span class="field-label">${escapeHtml(t("feeDay"))}</span>
        <input class="input" id="fee-day" inputmode="numeric" value="${group.billing_day || 1}"></label>
      <label class="field" id="fee-size-row"><span class="field-label">${escapeHtml(t("feeSize"))}</span>
        <input class="input" id="fee-size" inputmode="numeric" value="${group.package_lessons || 12}">
        <span class="stu-meta">${escapeHtml(t("feeSizeHelp"))}</span></label>
      <label class="field"><span class="field-label">${escapeHtml(t("feeDue"))}</span>
        <input class="input" id="fee-due" inputmode="numeric" value="${group.due_days ?? 5}"></label>
      <button type="button" class="primary" id="fee-save">${escapeHtml(t("save"))}</button>
    </div>
  `);
  document.querySelectorAll("[data-mode]").forEach((node) => {
    node.addEventListener("click", () => {
      document.querySelectorAll("[data-mode]").forEach((chip) => chip.classList.toggle("selected", chip === node));
      showMode(node.getAttribute("data-mode"));
    });
  });
  showMode(mode);
  document.getElementById("fee-save").addEventListener("click", (event) => {
    withBusy(event.currentTarget, () => save(groupId)).catch((err) => toast(t("error"), "err"));
  });
}

function showMode(mode) {
  document.getElementById("fee-day-row").hidden = mode !== "monthly";
  document.getElementById("fee-size-row").hidden = mode !== "package";
}

async function save(groupId) {
  const mode = document.querySelector("[data-mode].selected").getAttribute("data-mode");
  const body = {
    fee_mode: mode,
    fee_uzs: Number(document.getElementById("fee-amount").value || 0),
    due_days: Number(document.getElementById("fee-due").value || 0),
    billing_day: mode === "monthly" ? Number(document.getElementById("fee-day").value) : null,
    package_lessons: mode === "package" ? Number(document.getElementById("fee-size").value) : null,
  };
  await api(`/api/tutor/groups/${groupId}/fee`, { method: "PUT", body: JSON.stringify(body) });
  haptic("success");
  toast(t("saved"), "ok");
}

function hashParts() {
  return (location.hash || "").split("?")[0].replace(/^#\/?/, "").split("/").filter(Boolean);
}
