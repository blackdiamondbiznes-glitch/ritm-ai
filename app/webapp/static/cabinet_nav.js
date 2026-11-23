import { go, haptic, tg } from "./api.js";
import { t } from "./i18n.js";
import { icon } from "./icons.js";
import { escapeHtml } from "./ui.js";

/**
 * Teacher cabinet menu: a slim fixed bar with a hamburger on every cabinet screen,
 * opening a modal drawer with the sections. <dialog> + showModal() gives the focus
 * trap and Escape; the backdrop and Telegram's BackButton close it too.
 */
const SECTIONS = [
  ["home", "cabinet", "navCab", "home"],
  ["groups", "cabinet/groups", "grpNav", "users"],
  ["schedule", "cabinet/schedule", "schNav", "calendar"],
  ["students", "cabinet/students", "stuTitle", "cap"],
  ["lessons", "cabinet/lessons", "lesTitle", "book"],
  ["reminders", "cabinet/reminders", "remTitle", "bell"],
  ["fees", "cabinet/fees", "feeNav", "card"],
];
const KNOWN = new Set(SECTIONS.map(([id]) => id));

let bar = null;
let drawer = null;
let active = "home";
let backWasShown = false;

/** Section id for a cabinet route: `#/cabinet/12` and `#/cabinet/new` are student screens. */
export function cabinetSection(sub, id) {
  if (!sub) return id ? "students" : "home";
  if (sub === "new") return "students";
  return KNOWN.has(sub) ? sub : "";
}

function label(section) {
  const row = SECTIONS.find(([id]) => id === section);
  return t(row ? row[2] : "navCab");
}

function ensureBar() {
  if (bar) return bar;
  bar = document.createElement("div");
  bar.className = "cab-top";
  bar.hidden = true;
  bar.innerHTML = `<button type="button" class="cab-menu" aria-haspopup="dialog" aria-expanded="false"
    aria-controls="cab-drawer" aria-label="${escapeHtml(t("cabMenuOpen"))}">${icon("menu")}</button>
    <span class="cab-top-title"></span>`;
  bar.querySelector(".cab-menu").addEventListener("click", openCabinetMenu);
  document.body.prepend(bar);
  return bar;
}

function ensureDrawer() {
  if (drawer) return drawer;
  drawer = document.createElement("dialog");
  drawer.id = "cab-drawer";
  drawer.className = "cab-drawer";
  drawer.setAttribute("aria-labelledby", "cab-drawer-title");
  drawer.addEventListener("click", (event) => {
    if (event.target === drawer) closeCabinetMenu();
    const item = event.target.closest("[data-cab-go]");
    if (item) {
      haptic("light");
      const route = item.getAttribute("data-cab-go");
      closeCabinetMenu();
      go(route);
    }
    if (event.target.closest("[data-cab-close]")) closeCabinetMenu();
  });
  drawer.addEventListener("close", afterClose);
  document.body.append(drawer);
  return drawer;
}

function paintDrawer() {
  const items = SECTIONS.map(([id, route, key, name]) => {
    const on = id === active;
    return `<li><button type="button" class="cab-item${on ? " on" : ""}" data-cab-go="${route}"${on ? ' aria-current="page"' : ""}>
      ${icon(name)}<span>${escapeHtml(t(key))}</span></button></li>`;
  }).join("");
  drawer.innerHTML = `<div class="cab-drawer-body">
    <div class="cab-drawer-head">
      <h2 id="cab-drawer-title">${escapeHtml(t("cabMenuTitle"))}</h2>
      <button type="button" class="cab-close" data-cab-close aria-label="${escapeHtml(t("cabMenuClose"))}">${icon("close")}</button>
    </div>
    <ul class="cab-list">${items}</ul>
  </div>`;
}

export function openCabinetMenu() {
  ensureDrawer();
  if (drawer.open) return;
  haptic("light");
  paintDrawer();
  if (typeof drawer.showModal === "function") drawer.showModal();
  else drawer.setAttribute("open", "");
  const current = drawer.querySelector(".cab-item.on") || drawer.querySelector(".cab-item");
  if (current) current.focus();
  if (bar) bar.querySelector(".cab-menu").setAttribute("aria-expanded", "true");
  document.documentElement.classList.add("cab-locked");
  const back = tg && tg.BackButton;
  if (back) {
    backWasShown = Boolean(back.isVisible);
    back.show();
  }
}

/** Closes the drawer; returns true when it was open (so BackButton stops there). */
export function closeCabinetMenu() {
  if (!drawer || !drawer.open) return false;
  if (typeof drawer.close === "function") drawer.close();
  else {
    drawer.removeAttribute("open");
    afterClose();
  }
  return true;
}

function afterClose() {
  document.documentElement.classList.remove("cab-locked");
  if (bar) {
    const button = bar.querySelector(".cab-menu");
    button.setAttribute("aria-expanded", "false");
    if (!bar.hidden) button.focus({ preventScroll: true });
  }
  const back = tg && tg.BackButton;
  if (back && !backWasShown) back.hide();
}

/** Called on every route: shows the bar only on teacher cabinet screens. */
export function syncCabinetMenu(on, section = "home") {
  if (!on) {
    closeCabinetMenu();
    if (bar) bar.hidden = true;
    document.body.classList.remove("has-cab-top");
    return;
  }
  active = section;
  ensureBar().hidden = false;
  bar.querySelector(".cab-top-title").textContent = label(section);
  bar.querySelector(".cab-menu").setAttribute("aria-label", t("cabMenuOpen"));
  document.body.classList.add("has-cab-top");
}
