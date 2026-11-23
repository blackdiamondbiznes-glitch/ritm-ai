import { isManager, isStudent, isTutor, state, tg } from "./api.js";

const ROLE_KEY = "ritm.role";

function saved() {
  try {
    return localStorage.getItem(ROLE_KEY);
  } catch {
    return null;
  }
}

function save(role) {
  try {
    localStorage.setItem(ROLE_KEY, role);
  } catch {
    /* private mode: the choice lasts for this session only */
  }
}

/** Read a one-shot teacher/student hint, then leave the hash usable as a route. No buttons are drawn. */
export function applyRoleHint() {
  const hash = location.hash || "";
  const hinted = hash.match(/^#role=(teacher|student)$/);
  const query = new URLSearchParams(location.search);
  const roleQuery = query.get("role");
  const startapp = query.get("startapp");
  const start = tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param;
  let role = null;
  if (hash === "#/cabinet" || startapp === "cabinet" || start === "cabinet") role = "teacher";
  else if (hinted) role = hinted[1];
  else if (roleQuery === "teacher" || roleQuery === "student") role = roleQuery;
  else if (start === "teacher" || start === "student") role = start;
  if (!role) return null;
  save(role);
  if (hinted) history.replaceState(null, "", "#/home");
  if (role === "teacher" && (hash === "#/cabinet" || startapp === "cabinet" || start === "cabinet")) {
    if (!hash.startsWith("#/cabinet")) history.replaceState(null, "", "#/cabinet");
  }
  return role;
}

export function modes() {
  return (state.dash && state.dash.modes) || { teaching: [], learning: [], pending: [] };
}

function learns() {
  return (modes().learning || []).length > 0;
}

/** This account both runs a cabinet and attends one: only then can the mode change. */
export function bothRoles() {
  return isTutor() && learns();
}

/** Teacher when the account teaches, unless the remembered choice is student and both exist. */
export function chosenRole() {
  const teaching = isTutor();
  const learning = learns();
  if (teaching && learning) return saved() === "student" ? "student" : "teacher";
  if (teaching) return "teacher";
  if (learning) return "student";
  return "";
}

/** The student app (Bosh / Darslar / Profil) is shown. */
export function studentMode() {
  return (isStudent() && !isManager() && !isTutor()) || chosenRole() === "student";
}

/** Flip the remembered mode for a two-role account and return the new one. */
export function switchRole() {
  const next = chosenRole() === "student" ? "teacher" : "student";
  save(next);
  return next;
}
