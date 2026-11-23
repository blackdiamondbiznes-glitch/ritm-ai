import { load, state } from "./api.js";
import { icon } from "./icons.js";
import { bindJoin, joinCard } from "./join_card.js";
import { money } from "./money.js";
import { current, escapeHtml, setHtml, showError, skeleton, t } from "./ui.js";

export const LEARNING = "/api/me/learning";
const WEEK = "/api/me/sessions?days=7";
/** Paths the student app reads; warmed after bootstrap. */
export const STUDY_PATHS = [LEARNING, WEEK];
const FRESH = { maxAge: 20000 };
const TZ = "Asia/Tashkent";
const SOON_DAYS = 2;
const UNDATED_MAX = 5;
const WEEKDAY = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 };
const MARK = {
  present: "attPresent",
  late: "attLate",
  absent: "attAbsent",
  excused: "attExcused",
};

/* ---------- screens ---------- */

/** Bosh: what to do next, the next lesson, the nearest homework, the fee. */
export async function renderStudy(seq) {
  setHtml(skeleton("home"));
  try {
    const data = await load(LEARNING, FRESH);
    if (!current(seq)) return;
    paintToday(data);
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

/** Darslar: next lesson, this week with dates, every open homework. */
export async function renderAgenda(seq) {
  setHtml(skeleton("list"));
  try {
    const [data, week] = await Promise.all([load(LEARNING, FRESH), load(WEEK, FRESH).catch(() => [])]);
    if (!current(seq)) return;
    paintAgenda(data, Array.isArray(week) ? week : []);
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

export async function renderStudyDetail(groupId, seq) {
  let data;
  try {
    data = await load(LEARNING, FRESH);
  } catch (err) {
    if (current(seq)) showError(err);
    return;
  }
  if (!current(seq)) return;
  const item = (data.groups || []).find((row) => row.group.id === Number(groupId));
  if (!item) paintToday(data);
  else paintDetail(item);
}

function paintToday(data) {
  const groups = data.groups || [];
  const pending = data.pending || [];
  const head = header(greeting(), longDate(todayIso(), false));
  if (!groups.length && !pending.length) {
    setHtml(`${head}${joinCard()}`);
    bindJoin();
    return;
  }
  const body = groups.length ? `${nextCard(groups)}${homeworkCard(groups)}${feeCard(groups)}` : "";
  setHtml(`${head}${checklist(groups, pending)}${body}`);
}

function paintAgenda(data, week) {
  const groups = data.groups || [];
  const head = header(t("navAgenda"), t("agendaLead"));
  if (!groups.length) {
    const wait = (data.pending || []).length ? t("learnPending") : t("agendaEmpty");
    setHtml(`${head}<div class="card"><p class="stu-meta">${escapeHtml(wait)}</p></div>`);
    return;
  }
  setHtml(`${head}${nextCard(groups)}${weekCard(week, groups)}${homeworkList(groups)}`);
}

function paintDetail(item) {
  const group = item.group;
  setHtml(`
    ${header(`${group.name || ""}${group.level ? ` · ${group.level}` : ""}`, [group.teacher_name, whenDays(group)].filter(Boolean).join(" · "))}
    ${box(attTitle(item.attendance), markRows(item.attendance))}
    ${box(t("learnHomework"), homeworkRows(item.homework))}
    ${box(t("learnScores"), scoreRows(item.scores))}
    ${box(t("learnRankTitle"), rankRows(item.ranking))}
  `);
}

/* ---------- Bosh blocks ---------- */

function checklist(groups, pending) {
  const rows = [];
  if (groups.length) rows.push(check(t("prepJoin"), t("stDone"), "ok"));
  else rows.push(check(t("prepJoin"), t("learnPending"), "warn", pending.map((row) => row.group_name).join(", ")));
  const due = datedHomework(groups);
  if (due.length) {
    const soon = due.filter((row) => row.days <= SOON_DAYS).length;
    rows.push(soon ? check(t("prepHw"), t("hwSoon", { n: soon }), "warn") : check(t("prepHw"), t("hwOpen", { n: due.length }), ""));
  }
  const bill = pickFee(groups);
  if (bill) {
    const status = feeStatus(bill.fee);
    rows.push(check(t("prepFee"), status.label, status.tone));
  }
  return box(t("prepTitle"), rows.join(""));
}

function check(label, status, tone, sub = "") {
  return `<div class="check-row">
    <div class="check-text"><div class="check-label">${escapeHtml(label)}</div>${sub ? `<div class="stu-meta">${escapeHtml(sub)}</div>` : ""}</div>
    ${pill(status, tone)}
  </div>`;
}

/** The running or soonest lesson across all groups, with the online link when the teacher set one. */
function nextCard(groups) {
  const item = groups
    .filter((row) => row.next_session && row.next_session.starts_at)
    .sort((a, b) => Date.parse(a.next_session.starts_at) - Date.parse(b.next_session.starts_at))[0];
  if (!item) return box(t("nextLesson"), `<p class="stu-meta">${escapeHtml(t("nextNone"))}</p>`, "hero-next");
  const session = item.next_session;
  const group = item.group;
  const live = Date.parse(session.starts_at) <= Date.now();
  const level = group.level ? ` · ${group.level}` : "";
  return box(
    t("nextLesson"),
    `<div class="hero-date">${escapeHtml(live ? t("liveNow") : longDate(isoDay(session.starts_at), true))}</div>
    <div class="hero-time">${escapeHtml(timeRange(session))}</div>
    <a class="hero-group" href="#/study/${Number(group.id)}">${escapeHtml(`${group.name || ""}${level}`)}</a>
    ${group.teacher_name ? `<div class="stu-meta">${escapeHtml(group.teacher_name)}</div>` : ""}
    ${joinButton(session)}`,
    "hero-next",
  );
}

function homeworkCard(groups) {
  const first = datedHomework(groups)[0];
  if (!first) return box(t("learnHomework"), `<p class="stu-meta">${escapeHtml(t("hwNone"))}</p>`);
  return box(t("learnHomework"), homeworkLine(first));
}

function feeCard(groups) {
  const bill = pickFee(groups);
  if (!bill) return "";
  const fee = bill.fee;
  const status = feeStatus(fee);
  const amount = fee.lessons_total != null ? t("learnPack", { used: fee.lessons_used || 0, total: fee.lessons_total }) : money(fee.amount);
  let sub = "";
  if (fee.status === "overdue") sub = t("feeLate", { when: longDay(fee.due_on) });
  else if (fee.status === "due" && fee.due_on) sub = t("dueOn", { when: longDay(fee.due_on) });
  return box(
    t("feeStatusTitle"),
    `<div class="check-row">
      <div class="check-text"><div class="check-label">${escapeHtml(`${bill.group.name || ""} · ${amount}`)}</div>${sub ? `<div class="stu-meta">${escapeHtml(sub)}</div>` : ""}</div>
      ${pill(status.label, status.tone)}
    </div>`,
  );
}

/* ---------- Darslar blocks ---------- */

function weekCard(week, groups) {
  const byId = new Map(groups.map((row) => [row.group.id, row.group]));
  const rows = week
    .filter((row) => row.starts_at)
    .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at))
    .map((row) => dayRow(row, byId.get(row.group_id)))
    .join("");
  return box(t("weekTitle"), rows || `<p class="stu-meta">${escapeHtml(t("weekEmpty"))}</p>`);
}

function dayRow(row, group) {
  const parts = partsOf(row.starts_at);
  const name = group ? `${group.name}${group.level ? ` · ${group.level}` : ""}` : row.group_name || row.title || "";
  const today = isoDay(row.starts_at) === todayIso();
  const cancelled = row.status === "cancelled";
  const ended = Date.parse(row.ends_at || row.starts_at) < Date.now();
  const meta = [timeRange(row), today ? t("todayTag") : ""].filter(Boolean).join(" · ");
  const tag = cancelled ? pill(t("lesCancelled"), "bad") : today && !ended ? pill(t("dueToday"), "warn") : "";
  const cls = `day-row${ended || cancelled ? " past" : ""}`;
  const inner = `<div class="day-block"><b>${parts.day}</b><small>${escapeHtml(`${t(`day${parts.weekday}`).toLowerCase()}, ${t(`learnM${parts.month}`)}`)}</small></div>
    <div class="day-main"><div class="chat-name">${escapeHtml(name)}</div><div class="stu-meta">${escapeHtml(meta)}</div></div>${tag}`;
  return row.group_id ? `<a class="${cls}" href="#/study/${Number(row.group_id)}">${inner}</a>` : `<div class="${cls}">${inner}</div>`;
}

function homeworkList(groups) {
  const dated = datedHomework(groups);
  const undated = allHomework(groups).filter((row) => row.days == null).slice(0, UNDATED_MAX);
  const rows = [...dated, ...undated].map(homeworkLine).join("");
  return box(t("hwListTitle"), rows || `<p class="stu-meta">${escapeHtml(t("learnNoHw"))}</p>`);
}

function homeworkLine(row) {
  const when = row.days == null ? "" : t("dueOn", { when: longDay(row.due_on) });
  const sub = [row.group, when].filter(Boolean).join(" · ");
  return `<div class="check-row">
    <div class="check-text"><div class="check-label">${escapeHtml(row.topic || "")}</div>
      ${row.text ? `<div class="hw-text">${escapeHtml(row.text)}</div>` : ""}
      ${sub ? `<div class="stu-meta">${escapeHtml(sub)}</div>` : ""}</div>
    ${row.days == null ? "" : pill(relDays(row.days), row.days <= SOON_DAYS ? "warn" : "")}
  </div>`;
}

/* ---------- data helpers ---------- */

function allHomework(groups) {
  const out = [];
  groups.forEach((item) => {
    (item.homework || []).forEach((row) => {
      out.push({ ...row, group: item.group.name || "", days: row.due_on ? daysFromToday(row.due_on) : null });
    });
  });
  return out;
}

/** Homework with a due date today or later, soonest first. */
function datedHomework(groups) {
  return allHomework(groups)
    .filter((row) => row.days != null && row.days >= 0)
    .sort((a, b) => a.days - b.days);
}

/** Overdue first, then due, then the latest settled bill. */
function pickFee(groups) {
  const rank = { overdue: 0, due: 1 };
  return groups
    .filter((item) => item.fee && (item.fee.amount != null || item.fee.lessons_total != null))
    .map((item) => ({ group: item.group, fee: item.fee }))
    .sort((a, b) => (rank[a.fee.status] ?? 2) - (rank[b.fee.status] ?? 2))[0];
}

function feeStatus(fee) {
  if (fee.status === "paid" || fee.status === "waived") return { label: t("learnPaid"), tone: "ok" };
  if (fee.status === "overdue") return { label: t("feeDebt"), tone: "bad" };
  return { label: t("feeWait"), tone: "warn" };
}

/* ---------- group detail (unchanged content) ---------- */

function homeworkRows(rows) {
  if (!rows || !rows.length) return `<p class="stu-meta">${escapeHtml(t("learnNoHw"))}</p>`;
  return rows
    .map((item) => {
      const due = item.due_on ? ` · ${t("learnHwDue", { when: longDay(item.due_on) })}` : "";
      return `<div class="stu-row"><div>
        <div class="chat-name">${escapeHtml(item.topic || "")}</div>
        <div class="stu-meta">${escapeHtml(item.text || "")}${escapeHtml(due)}</div>
      </div></div>`;
    })
    .join("");
}

function rankRows(ranking) {
  if (!ranking || !ranking.length) return `<p class="stu-meta">${escapeHtml(t("rankEmpty"))}</p>`;
  return ranking
    .map((item) => {
      const mine = item.mine ? " stu-paid" : "";
      return `<div class="stu-row${mine}"><div class="chat-name">${item.rank}. ${escapeHtml(item.name || "")}</div><span>${item.total}</span></div>`;
    })
    .join("");
}

function scoreRows(scores) {
  if (!scores || !scores.length) return `<p class="stu-meta">${escapeHtml(t("learnNoScore"))}</p>`;
  return scores
    .map((item) => `<div class="stu-row"><div class="chat-name">${escapeHtml(item.topic || "")}</div><span>${item.score}</span></div>`)
    .join("");
}

function markRows(attendance) {
  const rows = (attendance && attendance.last) || [];
  if (!rows.length) return `<p class="stu-meta">${escapeHtml(t("attNone"))}</p>`;
  return rows
    .map((item) => {
      const label = t(MARK[item.status] || "attNone");
      const parts = partsOf(item.starts_at);
      return `<div class="stu-row"><div class="chat-name">${escapeHtml(`${parts.day}-${t(`learnM${parts.month}`)} ${parts.time}`)}</div><span>${escapeHtml(label)}</span></div>`;
    })
    .join("");
}

function attTitle(attendance) {
  if (!attendance || attendance.rate == null) return t("learnAtt");
  return `${t("learnAtt")} · ${Math.round(attendance.rate * 100)}%`;
}

/* ---------- markup ---------- */

function header(title, lead) {
  return `<div class="header"><h1>${escapeHtml(title)}</h1>${lead ? `<p>${escapeHtml(lead)}</p>` : ""}</div>`;
}

function box(title, body, cls = "") {
  return `<div class="card${cls ? ` ${cls}` : ""}"><div class="card-title">${escapeHtml(title)}</div>${body}</div>`;
}

function pill(label, tone) {
  return `<span class="st${tone ? ` st-${tone}` : ""}">${escapeHtml(label)}</span>`;
}

function joinButton(session) {
  const url = session && session.status !== "cancelled" ? session.meeting_url : "";
  if (!url) return "";
  return `<button type="button" class="primary join-btn" data-open-url="${escapeHtml(url)}">${icon("video")}<span>${escapeHtml(t("learnJoin"))}</span></button>`;
}

function greeting() {
  const user = (state.me && state.me.user) || {};
  const first = String(user.name || "").trim().split(/\s+/)[0];
  return first ? t("greet", { name: first }) : t("greetPlain");
}

function whenDays(group) {
  const days = (group.weekdays || []).map((day) => t(`day${day}`)).join(", ");
  return days ? `${days} · ${group.start}–${group.end}` : "";
}

/* ---------- dates (always Tashkent) ---------- */

function partsOf(iso) {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    year: "numeric",
    day: "numeric",
    month: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const bag = {};
  for (const part of fmt.formatToParts(new Date(iso))) bag[part.type] = part.value;
  return {
    year: Number(bag.year),
    day: Number(bag.day),
    month: Number(bag.month),
    weekday: WEEKDAY[bag.weekday] || 1,
    time: `${bag.hour}:${bag.minute}`,
  };
}

function isoDay(iso) {
  const parts = partsOf(iso);
  return `${parts.year}-${String(parts.month).padStart(2, "0")}-${String(parts.day).padStart(2, "0")}`;
}

function todayIso() {
  return isoDay(new Date().toISOString());
}

function daysFromToday(day) {
  const [y1, m1, d1] = todayIso().split("-").map(Number);
  const [y2, m2, d2] = String(day).slice(0, 10).split("-").map(Number);
  return Math.round((Date.UTC(y2, m2 - 1, d2) - Date.UTC(y1, m1 - 1, d1)) / 86400000);
}

/** "23-noyabr" / "23 ноября" / "23 November". */
function longDay(day) {
  if (!day || day.length < 10) return "";
  return t("dateDM", { day: Number(day.slice(8, 10)), month: t(`monthLong${Number(day.slice(5, 7))}`) });
}

/** "Dushanba, 23-noyabr"; with `relative`, today and tomorrow read as words. */
function longDate(day, relative) {
  const gap = daysFromToday(day);
  const [y, m, d] = day.split("-").map(Number);
  const weekday = ((new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7) + 1;
  let lead = t(`dayLong${weekday}`);
  if (relative && gap === 0) lead = t("dueToday");
  else if (relative && gap === 1) lead = t("dueTomorrow");
  return `${lead}, ${longDay(day)}`;
}

function relDays(days) {
  if (days === 0) return t("dueToday");
  if (days === 1) return t("dueTomorrow");
  return t("dueDays", { n: days });
}

function timeRange(session) {
  const start = partsOf(session.starts_at).time;
  return session.ends_at ? `${start}–${partsOf(session.ends_at).time}` : start;
}
