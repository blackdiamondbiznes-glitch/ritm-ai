import { setLang, t } from "./i18n.js";

/** Teacher web panel. Bosh is native; other sections embed the cabinet screens for now. */
const HOME_API = "/api/panel/home";
const TZ = "Asia/Tashkent";
const FRAMES = {
  schedule: "cabinet/schedule",
  groups: "cabinet/groups",
  students: "cabinet/students",
  attendance: "cabinet/schedule",
  fees: "cabinet/fees",
  reports: "cabinet/reports",
  settings: "profile",
};
const TITLES = {
  home: "pnlHome",
  schedule: "pnlSchedule",
  groups: "pnlGroups",
  students: "pnlStudents",
  attendance: "pnlAttendance",
  fees: "pnlFees",
  reports: "pnlReports",
  settings: "pnlSettings",
};
const main = document.getElementById("pn-main");
let me = null;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
}

function icon(name) {
  return `<svg class="ic" aria-hidden="true" focusable="false"><use href="#i-${name}"></use></svg>`;
}

function money(amount) {
  return `${String(Math.round(Number(amount) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, " ")} so'm`;
}

/* ---------- boot ---------- */

async function boot() {
  const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  bindChrome();
  window.addEventListener("hashchange", route);
  await route();
}

async function getJson(path) {
  const res = await fetch(path, { credentials: "same-origin", headers: { Accept: "application/json" } });
  if (res.status === 401) {
    const err = new Error("unauthorized");
    err.status = 401;
    throw err;
  }
  if (!res.ok) throw new Error("error");
  return res.json();
}

async function loadMe() {
  me = await getJson(HOME_API);
  await setLang(me.user.language || "uz");
  document.documentElement.lang = me.user.language || "uz";
  labelChrome();
  return me;
}

function parse() {
  const raw = (location.hash || "#/home").replace(/^#\/?/, "");
  if (raw.startsWith("open/")) return { section: "open", target: raw.slice(5) };
  return { section: TITLES[raw] ? raw : "home", target: "" };
}

async function route() {
  closeDrawer();
  const { section, target } = parse();
  try {
    if (!me || section === "home") await loadMe();
  } catch (err) {
    paintGate(err.status === 401);
    return;
  }
  markNav(section === "open" ? sectionFor(target) : section);
  if (!me.teacher) {
    paintNotTeacher();
    return;
  }
  if (section === "home") paintHome(me);
  else paintFrame(section === "open" ? target : FRAMES[section], section === "open" ? sectionFor(target) : section);
  main.focus({ preventScroll: true });
}

function sectionFor(target) {
  if (target.includes("/attendance")) return "attendance";
  if (target.startsWith("cabinet/fees")) return "fees";
  if (target.startsWith("cabinet/lessons") || target.startsWith("cabinet/schedule")) return "schedule";
  if (target.startsWith("cabinet/students")) return "students";
  return "home";
}

/* ---------- chrome ---------- */

function bindChrome() {
  document.getElementById("pn-scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeDrawer();
    closeMenu();
  });
  main.addEventListener("click", (event) => {
    const node = event.target instanceof Element ? event.target.closest("[data-act]") : null;
    if (!node) return;
    const act = node.getAttribute("data-act");
    if (act === "drawer") openDrawer();
    if (act === "menu") toggleMenu(node);
    if (act === "reload") route();
  });
  document.addEventListener("click", (event) => {
    const pop = document.getElementById("pn-pop");
    if (pop && !pop.hidden && !(event.target instanceof Element && event.target.closest(".pn-head-me"))) closeMenu();
  });
}

function labelChrome() {
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-label]").forEach((node) => {
    node.setAttribute("aria-label", t(node.getAttribute("data-i18n-label")));
  });
  const name = me.user.name || "";
  document.getElementById("pn-name").textContent = name;
  document.getElementById("pn-avatar").textContent = initials(name);
  document.getElementById("pn-switch").hidden = !me.both_roles;
}

function markNav(section) {
  document.querySelectorAll("#pn-nav [data-route]").forEach((node) => {
    const on = node.getAttribute("data-route") === section;
    node.classList.toggle("on", on);
    if (on) node.setAttribute("aria-current", "page");
    else node.removeAttribute("aria-current");
  });
}

function openDrawer() {
  document.getElementById("pn-side").classList.add("open");
  document.getElementById("pn-scrim").hidden = false;
  const first = document.querySelector("#pn-nav a");
  if (first) first.focus();
}

function closeDrawer() {
  document.getElementById("pn-side").classList.remove("open");
  document.getElementById("pn-scrim").hidden = true;
}

function toggleMenu(button) {
  const pop = document.getElementById("pn-pop");
  if (!pop) return;
  pop.hidden = !pop.hidden;
  button.setAttribute("aria-expanded", String(!pop.hidden));
}

function closeMenu() {
  const pop = document.getElementById("pn-pop");
  if (pop) pop.hidden = true;
  const button = document.querySelector('[data-act="menu"]');
  if (button) button.setAttribute("aria-expanded", "false");
}

function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  return (parts.slice(0, 2).map((part) => Array.from(part)[0] || "").join("") || "?").toUpperCase();
}

/** Page header: menu button and avatar menu show on phones; the sidebar covers desktop. */
function head(titleKey, lead, action = "") {
  const both = me && me.both_roles
    ? `<p class="pn-pop-note">${esc(t("pnlBothShort"))}</p><a href="/?role=student#/study">${esc(t("pnlToStudent"))}</a>`
    : "";
  return `<header class="pn-head">
    <button type="button" class="pn-icon-btn pn-only-phone" data-act="drawer" aria-label="${esc(t("pnlMenu"))}" aria-controls="pn-side">${icon("menu")}</button>
    <div class="pn-head-text"><p class="pn-eyebrow">${esc(t("pnlEyebrow"))}</p><h1>${esc(t(titleKey))}</h1>${lead ? `<p class="pn-lead">${esc(lead)}</p>` : ""}</div>
    <div class="pn-head-actions">${action}
      <div class="pn-head-me pn-only-phone">
        <button type="button" class="pn-avatar pn-avatar-btn" data-act="menu" aria-haspopup="true" aria-expanded="false" aria-controls="pn-pop" aria-label="${esc(me ? me.user.name : "")}">${esc(initials(me ? me.user.name : ""))}</button>
        <div class="pn-pop" id="pn-pop" hidden>${both}
          <form method="post" action="/panel/logout"><button type="submit" class="pn-pop-item">${esc(t("pnlLogout"))}</button></form>
        </div>
      </div>
    </div>
  </header>`;
}

/* ---------- screens ---------- */

function paintGate(signedOut) {
  main.innerHTML = `<section class="pn-gate-card pn-inline">
    <div class="pn-brand"><span class="pn-logo" aria-hidden="true">R</span>Ritm</div>
    <h1>${esc(t(signedOut ? "pnlSignedOut" : "error"))}</h1>
    <p>${esc(t(signedOut ? "pnlSignedOutLead" : "pnlRetryLead"))}</p>
    ${signedOut ? "" : `<button type="button" class="pn-btn pn-btn-primary" data-act="reload">${esc(t("retry"))}</button>`}
  </section>`;
}

function paintNotTeacher() {
  main.innerHTML = `${head("pnlHome", "")}<section class="pn-card"><h2>${esc(t("pnlNotTeacher"))}</h2>
    <p class="pn-muted">${esc(t("pnlNotTeacherLead"))}</p><a class="pn-btn pn-btn-primary" href="/">${esc(t("pnlOpenApp"))}</a></section>`;
}

function paintFrame(target, section) {
  const back = `<a class="pn-btn pn-btn-ghost" href="#/home">${icon("back")}<span>${esc(t("pnlHome"))}</span></a>`;
  main.innerHTML = `${head(TITLES[section] || "pnlHome", t("pnlFrameLead"), back)}
    <section class="pn-card pn-frame-card"><iframe class="pn-frame" src="/?embed=1#/${esc(target)}" title="${esc(t(TITLES[section] || "pnlHome"))}"></iframe></section>`;
}

function paintHome(data) {
  const lead = `${longDate(data.today)} · ${t("pnlHomeLead")}`;
  const add = `<a class="pn-btn pn-btn-primary pn-only-wide" href="#/open/cabinet/lessons/new">${icon("plus")}<span>${esc(t("pnlAddLesson"))}</span></a>`;
  const calm = !data.unmarked.count && !data.overdue.count && !data.requests.count && !(data.homework && data.homework.count);
  main.innerHTML = `${head("pnlHome", lead, add)}
    ${calm ? `<p class="pn-calm" role="status">${esc(t("pnlCalm"))}</p>` : ""}
    <section class="pn-kpis" aria-label="${esc(t("pnlAttention"))}">
      ${kpi("warn", "pnlUnmarked", "pnlUnmarkedShort", data.unmarked.count, unmarkedSub(data.unmarked), "pnlUnmarkedTag", unmarkedLink(data.unmarked))}
      ${kpi("bad", "pnlOverdue", "pnlOverdueShort", data.overdue.count, data.overdue.count ? money(data.overdue.sum_uzs) : t("pnlNone"), "pnlOverdueTag", "#/open/cabinet/fees")}
      ${data.homework ? kpi("accent", "pnlHomework", "pnlHomeworkShort", data.homework.count, "", "pnlHomeworkTag", "#/groups") : kpi("accent", "pnlIncome", "pnlIncomeShort", money(data.income.sum_uzs), t("pnlIncomeSub", { n: data.income.payments }), "pnlIncomeTag", "#/open/cabinet/reports")}
      ${kpi("ok", "pnlRequests", "pnlRequestsShort", data.requests.count, data.requests.first ? data.requests.first.student : t("pnlNone"), "pnlRequestsTag", "#/open/cabinet")}
    </section>
    <section class="pn-card pn-today" aria-labelledby="pn-today-title">
      <h2 id="pn-today-title">${esc(t("pnlToday"))}</h2>
      ${todayTable(data.lessons)}
      ${todayList(data.lessons)}
    </section>`;
}

function kpi(tone, label, short, value, sub, tag, href) {
  return `<a class="pn-kpi" href="${esc(href)}">
    <span class="pn-kpi-label"><span class="pn-wide">${esc(t(label))}</span><span class="pn-narrow">${esc(t(short))}</span></span>
    <span class="pn-kpi-value pn-${tone}">${esc(value)}</span>
    <span class="pn-kpi-sub"><span class="pn-wide">${esc(sub)}</span><span class="pn-narrow">${esc(t(tag))}</span></span>
  </a>`;
}

function unmarkedSub(block) {
  if (!block.count) return t("pnlNone");
  const days = [...new Set(block.items.map((item) => t(`dayLong${weekday(item.starts_at)}`).toLowerCase()))];
  return t("pnlUnmarkedSub", { days: days.join(", ") });
}

function unmarkedLink(block) {
  const first = block.items[0];
  return first ? `#/open/cabinet/schedule/${Number(first.id)}/attendance` : "#/attendance";
}

function todayTable(lessons) {
  if (!lessons.length) return `<p class="pn-muted pn-empty">${esc(t("pnlNoLessons"))}</p>`;
  const rows = lessons
    .map((row) => `<tr>
      <td class="pn-num">${esc(range(row))}</td>
      <td>${esc(title(row))}</td>
      <td class="pn-num">${esc(row.students)}</td>
      <td>${linkCell(row)}</td>
      <td class="pn-act">${action(row, false)}</td>
    </tr>`)
    .join("");
  return `<div class="pn-table-wrap pn-only-wide"><table class="pn-table">
    <thead><tr><th scope="col">${esc(t("pnlColTime"))}</th><th scope="col">${esc(t("pnlColGroup"))}</th><th scope="col">${esc(t("pnlColStudents"))}</th><th scope="col">${esc(t("pnlColLink"))}</th><th scope="col"><span class="pn-sr">${esc(t("pnlColAction"))}</span></th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function todayList(lessons) {
  if (!lessons.length) return "";
  const rows = lessons
    .map((row) => {
      const [hour, minute] = clock(row.starts_at).split(":");
      const meta = [t("pnlStudentsN", { n: row.students }), provider(row.meeting_url)].filter(Boolean).join(" · ");
      return `<li class="pn-row">
        <span class="pn-time"><b>${esc(hour)}</b><small>${esc(minute)}</small></span>
        <span class="pn-row-text"><b>${esc(title(row))}</b><small>${esc(meta)}</small></span>
        ${action(row, true)}
      </li>`;
    })
    .join("");
  return `<ul class="pn-list pn-only-phone">${rows}</ul>`;
}

function action(row, compact) {
  const roll = `#/open/cabinet/schedule/${Number(row.id)}/attendance`;
  if (row.marked) return `<a class="pn-btn pn-btn-ghost pn-btn-sm" href="${roll}">${esc(t(compact ? "pnlMarkedShort" : "pnlMarked"))}</a>`;
  if (Date.parse(row.starts_at) <= Date.now()) {
    return `<a class="pn-btn pn-btn-primary pn-btn-sm" href="${roll}">${esc(t(compact ? "pnlMarkShort" : "pnlMark"))}</a>`;
  }
  return `<span class="pn-tag">${esc(t(compact ? "pnlLaterShort" : "pnlLater"))}</span>`;
}

function linkCell(row) {
  if (!row.meeting_url) return `<span class="pn-muted" aria-label="${esc(t("pnlNoLink"))}">—</span>`;
  return `<a class="pn-link" href="${esc(row.meeting_url)}" target="_blank" rel="noopener noreferrer" aria-label="${esc(`${t("learnJoin")} · ${provider(row.meeting_url)}`)}">${esc(provider(row.meeting_url))}</a>`;
}

function provider(url) {
  if (!url) return "";
  try {
    const host = new URL(url).hostname;
    if (host.includes("meet.google")) return "Meet";
    if (host.includes("zoom")) return "Zoom";
    if (host.includes("teams")) return "Teams";
  } catch {
    return t("pnlLink");
  }
  return t("pnlLink");
}

function title(row) {
  return `${row.title || ""}${row.level ? ` · ${row.level}` : ""}`;
}

/* ---------- dates (Tashkent) ---------- */

function clock(iso) {
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
}

function range(row) {
  return row.ends_at ? `${clock(row.starts_at)}–${clock(row.ends_at)}` : clock(row.starts_at);
}

function weekday(iso) {
  const name = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short" }).format(new Date(iso));
  return { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 }[name] || 1;
}

function longDate(day) {
  const [y, m, d] = day.split("-").map(Number);
  const dow = ((new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7) + 1;
  return `${t(`dayLong${dow}`)}, ${t("dateDM", { day: d, month: t(`monthLong${m}`) })}`;
}

boot();
