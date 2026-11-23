import { escapeHtml, t } from "./ui.js";

export function groupTabs(group, active) {
  const tab = (mode, key, href) => {
    const on = mode === active ? " on" : "";
    return `<a class="seg-btn${on}" href="${href}">${escapeHtml(t(key))}</a>`;
  };
  const home = `#/cabinet/groups/${group.id}`;
  const roll = `#/cabinet/groups/${group.id}/attendance`;
  const fee = `#/cabinet/groups/${group.id}/fee`;
  const note = `#/cabinet/groups/${group.id}/notice`;
  const lead = group.start ? `<p>${escapeHtml(schedule(group))}</p>` : "";
  const bar = [
    tab("home", "grpNav", home),
    tab("roll", "attNav", roll),
    tab("fee", "feeNav", fee),
    tab("notice", "noticeNav", note),
  ].join("");
  return `<div class="seg cab-tabs">${bar}</div>
    <div class="header"><h1>${escapeHtml(group.name)}</h1>${lead}</div>`;
}

function schedule(group) {
  const days = (group.weekdays || []).map((day) => t(`day${day}`)).join(", ");
  const level = group.level ? ` · ${group.level}` : "";
  return `${days} · ${group.start}–${group.end}${level}`;
}
