import { go, state, tg } from "./api.js";
import { escapeHtml, t } from "./ui.js";

const ROLE_KEY = "ritm.role";

/** Read a one-shot teacher/student hint, then leave the hash usable as a route. */
export function applyRoleHint() {
  const hash = location.hash || "";
  const hinted = hash.match(/^#role=(teacher|student)$/);
  const query = new URLSearchParams(location.search).get("role");
  const start = tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param;
  let role = null;
  if (hinted) role = hinted[1];
  else if (query === "teacher" || query === "student") role = query;
  else if (start === "teacher" || start === "student") role = start;
  if (!role) return null;
  localStorage.setItem(ROLE_KEY, role);
  if (hinted) history.replaceState(null, "", "#/home");
  return role;
}

export function modes() {
  return (state.dash && state.dash.modes) || { teaching: [], learning: [], pending: [] };
}

/** Teacher when the account teaches, unless the saved choice is student and both exist. */
export function chosenRole() {
  const data = modes();
  const teaching = (data.teaching || []).length > 0;
  const learning = (data.learning || []).length > 0;
  if (teaching && learning) {
    const saved = localStorage.getItem(ROLE_KEY);
    return saved === "student" ? "student" : "teacher";
  }
  if (teaching) return "teacher";
  if (learning) return "student";
  return "";
}

/** Segmented switch. Hidden unless this account both teaches and studies. */
export function mountRoles() {
  const bar = document.getElementById("rolebar");
  if (!bar) return;
  const data = modes();
  const teaching = (data.teaching || []).length > 0;
  const learning = (data.learning || []).length > 0;
  if (!teaching || !learning) {
    bar.hidden = true;
    bar.replaceChildren();
    return;
  }
  const role = chosenRole();
  bar.hidden = false;
  bar.innerHTML = `<div class="chips">${button("teacher", role)}${button("student", role)}</div>`;
  bar.querySelectorAll("[data-role]").forEach((node) => {
    node.addEventListener("click", () => {
      const next = node.getAttribute("data-role");
      if (next !== "teacher" && next !== "student") return;
      localStorage.setItem(ROLE_KEY, next);
      mountRoles();
      go(next === "student" ? "study" : "cabinet");
    });
  });
}

function button(role, current) {
  const on = role === current ? " selected" : "";
  const label = role === "teacher" ? t("roleTeacher") : t("roleStudent");
  return `<button type="button" class="chip-btn${on}" data-role="${role}">${escapeHtml(label)}</button>`;
}
