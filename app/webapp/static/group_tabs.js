import { escapeHtml, t } from "./ui.js";

export function groupTabs(group, active) {
  const tab = (mode, key, href) => {
    const on = mode === active ? " on" : "";
    return `<a class="seg-btn${on}" href="${href}">${escapeHtml(t(key))}</a>`;
  };
  const home = `#/cabinet/groups/${group.id}`;
  const roll = `#/cabinet/groups/${group.id}/attendance`;
  const lead = group.start ? `<p>${escapeHtml(schedule(group))}</p>` : "";
  return `<div class="seg">${tab("home", "grpNav", home)}${tab("roll", "attNav", roll)}</div>
    <div class="header"><h1>${escapeHtml(group.name)}</h1>${lead}</div>`;
}

function schedule(group) {
  const days = (group.weekdays || []).map((day) => t(`day${day}`)).join(", ");
  const level = group.level ? ` · ${group.level}` : "";
  return `${days} · ${group.start}–${group.end}${level}`;
}
