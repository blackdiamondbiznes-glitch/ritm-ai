import { haptic, hasRole, isManager, isStudent, isTutor, parseRoute, tg } from "./api.js";
import { chosenRole } from "./roles.js";
import { t } from "./i18n.js";
import { currentVertical } from "./vertical.js";
import { clearMainButton } from "./main_btn.js";

/** Bottom tabs for the signed-in role. The server still checks every request. */
export function navTabs() {
  const vertical = currentVertical();
  const teacher = isTutor() && chosenRole() !== "student";
  const student = (isStudent() && !isManager() && !isTutor()) || chosenRole() === "student";
  if (teacher) {
    const tabs = [...vertical.teacherTabs];
    if (isManager()) tabs.push(...vertical.teacherCommunityTabs);
    if (hasRole("super_admin")) tabs.push("admin");
    tabs.push("profile");
    return tabs;
  }
  if (student) {
    const tabs = [...vertical.studentTabs];
    if (hasRole("member")) tabs.push(...vertical.studentCommunityTabs);
    tabs.push("profile");
    return tabs;
  }
  if (isManager()) {
    const tabs = ["home", "chats", "board", "report", "profile"];
    if (hasRole("super_admin")) tabs.splice(tabs.indexOf("profile"), 0, "admin");
    return tabs;
  }
  if (hasRole("member")) return ["home", "board", "history", "profile"];
  return ["home", "profile"];
}

export function bindNav() {
  const nav = document.getElementById("nav");
  if (!nav) return;
  nav.hidden = false;
  labelNav();
  nav.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      haptic("light");
      const tab = btn.getAttribute("data-tab");
      const next = `#/${tab}`;
      if (location.hash === next) window.dispatchEvent(new Event("hashchange"));
      else location.hash = next;
    });
  });
}

export function labelNav() {
  const nav = document.getElementById("nav");
  if (!nav) return;
  nav.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.getAttribute("data-i18n"));
  });
}

/** Cabinet or study root is that role's home, so the Telegram Back button stays hidden. */
export function isRoleHome(tab, sub, id) {
  if (tab === "cabinet") return !sub && !id;
  if (tab === "study" || tab === "boards") return !id;
  return false;
}

export function syncChrome() {
  clearMainButton();
  const { tab, sub, id } = parseRoute();
  const nav = document.getElementById("nav");
  if (nav) {
    nav.hidden = false;
    const tabs = navTabs();
    nav.querySelectorAll("[data-tab]").forEach((btn) => {
      const name = btn.getAttribute("data-tab");
      btn.hidden = !tabs.includes(name);
      const on = name === tab || (name === "cabinet" && tab === "cabinet") || (name === "study" && (tab === "study" || tab === "boards"));
      btn.classList.toggle("active", on && !btn.hidden);
    });
  }
  const back = tg && tg.BackButton;
  if (!back) return;
  const nested =
    !isRoleHome(tab, sub, id) &&
    (Boolean(id && tab !== "board") ||
      tab === "cabinet" ||
      tab === "study" ||
      tab === "boards" ||
      (sub && (tab === "admin" || tab === "profile")) ||
      (tab === "history" && !navTabs().includes("history")));
  if (nested) back.show();
  else back.hide();
}
