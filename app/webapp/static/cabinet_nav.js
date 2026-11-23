import { go, haptic } from "./api.js";
import { t } from "./i18n.js";
import { escapeHtml } from "./ui.js";

const ROUTES = {
  groups: "cabinet/groups",
  schedule: "cabinet/schedule",
  lessons: "cabinet/lessons",
  reminders: "cabinet/reminders",
  fees: "cabinet/fees",
};

export function cabinetSwitch(active) {
  const item = (id, key) => {
    const on = id === active ? " on" : "";
    return `<button type="button" class="seg-btn${on}" data-cab="${id}">${escapeHtml(t(key))}</button>`;
  };
  const keys = [
    ["groups", "grpNav"],
    ["schedule", "schNav"],
    ["students", "stuTitle"],
    ["lessons", "lesTitle"],
    ["reminders", "remTitle"],
    ["fees", "feeNav"],
  ];
  return `<div class="seg cab-switch">${keys.map(([id, key]) => item(id, key)).join("")}</div>`;
}

export function bindCabinetSwitch() {
  document.querySelectorAll("[data-cab]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      const section = node.getAttribute("data-cab");
      go(ROUTES[section] || "cabinet/students");
    });
  });
}
