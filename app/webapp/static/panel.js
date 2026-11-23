import { setLang } from "./i18n.js";
import { esc, head, icon, initials, money, provider, resetHandlers, state, t } from "./panel_kit.js";
import { renderGroups, renderStudents } from "./panel_people.js";
import { renderFees, renderReports } from "./panel_money.js";
import { renderAttendance, renderSchedule } from "./panel_schedule.js";
import { renderSettings } from "./panel_settings.js";

/** Teacher web panel shell: sign-in gate, sidebar/drawer, hash routes. Every section is native. */
const HOME_API = "/api/panel/home";
const TZ = "Asia/Tashkent";
const PAGES = {
  schedule: renderSchedule,
  groups: renderGroups,
  students: renderStudents,
  attendance: renderAttendance,
  fees: renderFees,
  reports: renderReports,
  settings: (main, parts) => renderSettings(main, parts, labelChrome),
};
const SECTIONS = new Set(["home", ...Object.keys(PAGES)]);
const main = document.getElementById("pn-main");
let me = null;

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
  state.me = me;
  await setLang(me.user.language || "uz");
  document.documentElement.lang = me.user.language || "uz";
  labelChrome();
  return me;
}

function parse() {
  const raw = (location.hash || "#/home").replace(/^#\/?/, "");
  const [section, ...parts] = raw.split("/").filter(Boolean);
  return SECTIONS.has(section) ? { section, parts } : { section: "home", parts: [] };
}

async function route() {
  closeDrawer();
  closeMenu();
  resetHandlers();
  const { section, parts } = parse();
  try {
    if (!me || section === "home") await loadMe();
  } catch (err) {
    paintGate(err.status === 401);
    return;
  }
  markNav(section);
  if (!me.teacher) {
    paintNotTeacher();
    return;
  }
  if (section === "home") paintHome(me);
  else await PAGES[section](main, parts);
  document.title = `${t(TITLES[section])} · Ritm`;
  main.focus({ preventScroll: true });
}

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
  main.innerHTML = `${head(t("pnlHome"), "")}<section class="pn-card"><h2>${esc(t("pnlNotTeacher"))}</h2>
    <p class="pn-muted">${esc(t("pnlNotTeacherLead"))}</p><a class="pn-btn pn-btn-primary" href="/">${esc(t("pnlOpenApp"))}</a></section>`;
}

function paintHome(data) {
  const lead = `${longDate(data.today)} · ${t("pnlHomeLead")}`;
  const add = `<a class="pn-btn pn-btn-primary pn-only-wide" href="#/schedule/new">${icon("plus")}<span>${esc(t("pnlAddLesson"))}</span></a>`;
  const calm = !data.unmarked.count && !data.overdue.count && !data.requests.count && !(data.homework && data.homework.count);
  main.innerHTML = `${head(t("pnlHome"), lead, add)}
    ${calm ? `<p class="pn-calm" role="status">${esc(t("pnlCalm"))}</p>` : ""}
    <section class="pn-kpis" aria-label="${esc(t("pnlAttention"))}">
      ${kpi("warn", "pnlUnmarked", "pnlUnmarkedShort", data.unmarked.count, unmarkedSub(data.unmarked), "pnlUnmarkedTag", unmarkedLink(data.unmarked))}
      ${kpi("bad", "pnlOverdue", "pnlOverdueShort", data.overdue.count, data.overdue.count ? money(data.overdue.sum_uzs) : t("pnlNone"), "pnlOverdueTag", "#/fees/overdue")}
      ${data.homework ? kpi("accent", "pnlHomework", "pnlHomeworkShort", data.homework.count, "", "pnlHomeworkTag", "#/groups") : kpi("accent", "pnlIncome", "pnlIncomeShort", money(data.income.sum_uzs), t("pnlIncomeSub", { n: data.income.payments }), "pnlIncomeTag", "#/reports")}
      ${kpi("ok", "pnlRequests", "pnlRequestsShort", data.requests.count, data.requests.first ? data.requests.first.student : t("pnlNone"), "pnlRequestsTag", "#/students/requests")}
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
  return first ? `#/attendance/${Number(first.id)}` : "#/attendance";
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
  const roll = `#/attendance/${Number(row.id)}`;
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
