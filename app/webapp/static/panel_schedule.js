import {
  addDays, api, busy, button, chips, clock, dayMonth, dayOf, dialog, empty, esc, failed, field, groupLabel,
  head, input, loading, longDay, mondayOf, on, provider, select, send, span, t, tag, toast, todayIso, wall,
  weekdayOf,
} from "./panel_kit.js";

/** Jadval (week grid + lesson card + roll) and Davomat (recent lessons + roll). */
const MARKS = [
  ["present", "attPresent", "pdShortPresent", "ok"],
  ["late", "attLate", "pdShortLate", "warn"],
  ["absent", "attAbsent", "pdShortAbsent", "bad"],
  ["excused", "attExcused", "pdShortExcused", "muted"],
];
const STATUS = { scheduled: "lesScheduled", done: "lesDone", cancelled: "lesCancelled" };
const ATT_DAYS = 14;

const week = { anchor: "", group: "", picked: null };

/* ---------- Jadval ---------- */

export async function renderSchedule(main, parts) {
  const title = t("pnlSchedule");
  if (!week.anchor) week.anchor = mondayOf(todayIso());
  if (parts[0] === "new") {
    history.replaceState(null, "", "#/schedule");
    week.openAdd = true;
  } else if (parts[0]) {
    week.picked = Number(parts[0]);
  }
  loading(main, title);
  let rows;
  let groups;
  try {
    [rows, groups] = await Promise.all([
      api(`/api/tutor/sessions?from=${week.anchor}&to=${addDays(week.anchor, 6)}`),
      api("/api/tutor/groups").then((data) => data.groups || []),
    ]);
  } catch (err) {
    failed(main, title, err);
    return;
  }
  paintWeek(main, rows, groups);
  if (week.openAdd) {
    week.openAdd = false;
    addSession(main, groups);
  }
}

function paintWeek(main, rows, groups) {
  const shown = rows.filter((row) => !week.group || String(row.group_id) === week.group);
  const days = Array.from({ length: 7 }, (_, index) => addDays(week.anchor, index));
  const today = todayIso();
  if (!shown.some((row) => row.id === week.picked)) {
    const first = shown.find((row) => dayOf(row.starts_at) === today) || shown.find((row) => dayOf(row.starts_at) >= today) || shown[0];
    week.picked = first ? first.id : null;
  }
  const picked = shown.find((row) => row.id === week.picked) || null;
  const lead = `${dayMonth(days[0])} – ${dayMonth(days[6])} · ${t("pdSchLead")}`;
  const add = button(t("pdAddSession"), 'data-act-add', "primary", "plus");
  const filters = [["", t("pdAllGroups")], ...groups.map((group) => [String(group.id), groupLabel(group)])];
  main.innerHTML = `${head(t("pnlSchedule"), lead, add)}
    <div class="pd-toolbar">
      ${chips(filters, week.group, "data-group")}
      <div class="pd-weeknav">
        <button type="button" class="pn-icon-btn" data-shift="-7" aria-label="${esc(t("pdPrevWeek"))}">‹</button>
        <button type="button" class="pn-btn pn-btn-ghost pn-btn-sm" data-shift="0">${esc(t("pdThisWeek"))}</button>
        <button type="button" class="pn-icon-btn" data-shift="7" aria-label="${esc(t("pdNextWeek"))}">›</button>
      </div>
    </div>
    <section class="pd-week" aria-label="${esc(t("pnlSchedule"))}">
      ${days.map((iso) => dayCell(iso, shown, today)).join("")}
    </section>
    <div class="pd-split">
      <section class="pn-card" id="pd-roll" aria-live="polite">${picked ? "" : empty(t("pdPickLesson"))}</section>
      <aside class="pn-card" id="pd-info">${picked ? infoCard(picked) : empty(shown.length ? t("pdPickLesson") : t("pdWeekEmpty"))}</aside>
    </div>`;
  if (picked) mountRoll(main.querySelector("#pd-roll"), picked);
  on(main, "data-group", (node) => {
    week.group = node.getAttribute("data-group");
    paintWeek(main, rows, groups);
  });
  on(main, "data-shift", (node) => {
    const step = Number(node.getAttribute("data-shift"));
    week.anchor = step ? addDays(week.anchor, step) : mondayOf(todayIso());
    week.picked = null;
    renderSchedule(main, []);
  });
  on(main, "data-pick", (node) => {
    week.picked = Number(node.getAttribute("data-pick"));
    history.replaceState(null, "", `#/schedule/${week.picked}`);
    paintWeek(main, rows, groups);
    const target = main.querySelector(".pd-split");
    if (target && window.matchMedia("(max-width: 760px)").matches) target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  on(main, "data-act-add", () => addSession(main, groups));
  bindInfo(main, picked);
}

function dayCell(iso, rows, today) {
  const list = rows.filter((row) => dayOf(row.starts_at) === iso);
  const pills = list
    .map((row) => {
      const tone = row.status === "cancelled" ? " cancelled" : row.status === "done" ? " done" : "";
      const on = row.id === week.picked ? " on" : "";
      return `<button type="button" class="pd-pill${tone}${on}" data-pick="${row.id}" aria-pressed="${row.id === week.picked}">
        <b>${esc(clock(row.starts_at))}</b> ${esc(row.group_name || row.title)}</button>`;
    })
    .join("");
  const now = iso === today ? " today" : "";
  return `<div class="pd-day-cell${now}"${iso === today ? ' aria-current="date"' : ""}>
    <span class="pd-day-name">${esc(t(`day${weekdayOf(iso)}`))}</span><span class="pd-day-num">${Number(iso.slice(8))}</span>
    <div class="pd-pills">${pills}</div></div>`;
}

function infoCard(row) {
  const when = `${longDay(dayOf(row.starts_at))} · ${span(row)}`;
  const start = wall(row.starts_at);
  const end = row.ends_at ? clock(row.ends_at) : "";
  const link = row.meeting_url
    ? `<a class="pn-link" href="${esc(row.meeting_url)}" target="_blank" rel="noopener noreferrer">${esc(provider(row.meeting_url))}</a>`
    : `<span class="pn-muted">${esc(t("pnlNoLink"))}</span>`;
  return `<h2>${esc(t("pdLessonInfo"))}</h2>
    <p class="pd-big">${esc(row.group_name || row.title)}</p>
    <p class="pn-muted">${esc(when)}</p>
    <p class="pd-line">${esc(t("pnlLink"))}: ${link}</p>
    <p class="pd-line">${tag(row.status === "cancelled" ? "bad" : row.status === "done" ? "ok" : "muted", t(STATUS[row.status] || "lesScheduled"))}</p>
    <form class="pd-form pd-inline-form" id="pd-edit" novalidate>
      ${field(t("pdTitle"), input("title", row.title, 'maxlength="120" required'))}
      <div class="pd-row2">
        ${field(t("pdStart"), input("starts_at", start, 'type="datetime-local" required'))}
        ${field(t("pdEnd"), input("end", end, 'type="time"'))}
      </div>
      ${field(t("pnlLink"), input("meeting_url", row.meeting_url || "", 'type="url" inputmode="url" maxlength="500" placeholder="https://meet.google.com/…"'))}
      <div class="pd-actions">
        <button type="submit" class="pn-btn pn-btn-primary">${esc(t("save"))}</button>
        ${row.status === "scheduled" ? button(t("pdMarkDone"), 'data-status="done"') : ""}
        ${row.status !== "cancelled" ? button(t("pdCancelLesson"), 'data-status="cancelled"', "danger") : button(t("pdRestore"), 'data-status="scheduled"')}
      </div>
    </form>`;
}

function bindInfo(main, row) {
  if (!row) return;
  const form = main.querySelector("#pd-edit");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const start = String(data.get("starts_at") || "");
    busy(form.querySelector('[type="submit"]'), async () => {
      await send(`/api/tutor/sessions/${row.id}`, "PATCH", {
        title: data.get("title"),
        starts_at: start,
        ends_at: endWall(start, String(data.get("end") || "")),
        meeting_url: String(data.get("meeting_url") || "").trim(),
      });
      toast(t("saved"));
      renderSchedule(main, [String(row.id)]);
    });
  });
  form.querySelectorAll("[data-status]").forEach((node) => {
    node.addEventListener("click", () =>
      busy(node, async () => {
        await send(`/api/tutor/sessions/${row.id}`, "PATCH", { status: node.getAttribute("data-status") });
        toast(t("saved"));
        renderSchedule(main, [String(row.id)]);
      }),
    );
  });
}

function addSession(main, groups) {
  if (!groups.length) {
    toast(t("pdNeedGroup"), "err");
    return;
  }
  const day = todayIso() >= week.anchor && todayIso() <= addDays(week.anchor, 6) ? todayIso() : week.anchor;
  const first = groups[0];
  const fields = `
    ${field(t("pnlColGroup"), select("group_id", groups.map((group) => [group.id, groupLabel(group)]), first.id))}
    ${field(t("pdTitle"), input("title", t("pdLessonDefault"), 'maxlength="120" required'))}
    ${field(t("pdDate"), input("day", day, 'type="date" required'))}
    <div class="pd-row2">
      ${field(t("pdStart"), input("start", first.start || "18:00", 'type="time" required'))}
      ${field(t("pdEnd"), input("end", first.end || "19:30", 'type="time" required'))}
    </div>
    ${field(t("pnlLink"), input("meeting_url", "", 'type="url" inputmode="url" maxlength="500" placeholder="https://meet.google.com/…"'), t("pdLinkHint"))}`;
  dialog(t("pdAddSession"), fields, async (form) => {
    const data = new FormData(form);
    const start = `${data.get("day")}T${data.get("start")}`;
    const row = await send(`/api/tutor/groups/${Number(data.get("group_id"))}/sessions`, "POST", {
      title: data.get("title"),
      starts_at: start,
      ends_at: endWall(start, String(data.get("end") || "")),
      meeting_url: String(data.get("meeting_url") || "").trim(),
    });
    toast(t("saved"));
    week.anchor = mondayOf(String(data.get("day")));
    renderSchedule(main, [String(row.id)]);
  });
}

/** End on the lesson's day; an end before the start belongs to the next day. */
function endWall(start, time) {
  if (!start || !time) return "";
  const day = time < start.slice(11, 16) ? addDays(start.slice(0, 10), 1) : start.slice(0, 10);
  return `${day}T${time}`;
}

/* ---------- Davomat ---------- */

export async function renderAttendance(main, parts) {
  const title = t("pnlAttendance");
  loading(main, title);
  const today = todayIso();
  let rows;
  let unmarked;
  try {
    const [sessions, home] = await Promise.all([
      api(`/api/tutor/sessions?from=${addDays(today, 1 - ATT_DAYS)}&to=${today}`),
      api("/api/panel/home"),
    ]);
    const now = Date.now();
    rows = sessions
      .filter((row) => row.group_id && row.status !== "cancelled" && Date.parse(row.starts_at) <= now)
      .sort((a, b) => Date.parse(b.starts_at) - Date.parse(a.starts_at));
    unmarked = new Set((home.unmarked.items || []).map((item) => item.id));
  } catch (err) {
    failed(main, title, err);
    return;
  }
  let picked = Number(parts[0]) || (rows.find((row) => unmarked.has(row.id)) || rows[0] || {}).id;
  const paint = () => {
    const lead = t("pdAttLead", { n: unmarked.size });
    main.innerHTML = `${head(title, lead)}
      <div class="pd-split pd-split-list">
        <section class="pn-card"><h2>${esc(t("pdRecent", { n: ATT_DAYS }))}</h2>${rows.length ? `<ul class="pd-pick-list">${rows.map((row) => pickRow(row, row.id === picked, unmarked)).join("")}</ul>` : empty(t("pdNoRecent"))}</section>
        <section class="pn-card" id="pd-roll" aria-live="polite">${picked ? "" : empty(t("pdPickLesson"))}</section>
      </div>`;
    const row = rows.find((item) => item.id === picked);
    if (row) {
      mountRoll(main.querySelector("#pd-roll"), row, (marked) => {
        if (marked) unmarked.delete(row.id);
        else unmarked.add(row.id);
        paint();
      });
    }
  };
  paint();
  on(main, "data-pick", (node) => {
    picked = Number(node.getAttribute("data-pick"));
    history.replaceState(null, "", `#/attendance/${picked}`);
    paint();
    const roll = main.querySelector("#pd-roll");
    if (roll && window.matchMedia("(max-width: 760px)").matches) roll.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function pickRow(row, onNow, unmarked) {
  const ended = Date.parse(row.ends_at || row.starts_at) <= Date.now();
  const state = unmarked.has(row.id) ? tag("warn", t("pnlUnmarkedTag")) : ended ? tag("ok", t("pnlMarked")) : tag("accent", t("pdNow"));
  return `<li><button type="button" class="pd-pick${onNow ? " on" : ""}" data-pick="${row.id}" aria-pressed="${onNow}">
    <span class="pd-pick-text"><b>${esc(row.group_name || row.title)}</b><small>${esc(`${longDay(dayOf(row.starts_at))} · ${span(row)}`)}</small></span>${state}</button></li>`;
}

/* ---------- roll (shared) ---------- */

/** Attendance sheet for one group lesson inside `box`. `done(marked)` runs after a save. */
export async function mountRoll(box, row, done) {
  if (!row.group_id) {
    box.innerHTML = `<h2>${esc(t("pnlAttendance"))}</h2>${empty(t("pdSoloLesson"))}`;
    return;
  }
  box.innerHTML = `<p class="pn-loading">${esc(t("loading"))}</p>`;
  let data;
  try {
    data = await api(`/api/tutor/sessions/${row.id}/attendance`);
  } catch (err) {
    box.innerHTML = `<p>${esc(t("error"))}</p>`;
    return;
  }
  const marks = new Map((data.students || []).map((item) => [item.student_id, item.status]));
  const future = dayOf(data.starts_at) > todayIso();
  const paint = () => {
    const students = data.students || [];
    const left = students.filter((item) => !marks.get(item.student_id)).length;
    const lines = students
      .map((item) => {
        const current = marks.get(item.student_id);
        const buttons = MARKS.map(([status, full, short, tone]) => {
          const pressed = current === status;
          return `<button type="button" class="pd-mark pd-mark-${tone}${pressed ? " on" : ""}" data-mark="${status}" data-student="${item.student_id}" aria-pressed="${pressed}" aria-label="${esc(`${item.name}: ${t(full)}`)}" title="${esc(t(full))}"${future ? " disabled" : ""}>${esc(t(short))}</button>`;
        }).join("");
        const label = current ? t(MARKS.find((mark) => mark[0] === current)[1]) : t("pnlUnmarkedTag");
        return `<li class="pd-roll-row"><span class="pd-roll-name">${esc(item.name)}</span>
          <span class="pd-marks" role="group" aria-label="${esc(item.name)}">${buttons}</span>
          <span class="pd-roll-state pn-muted">${esc(label)}</span></li>`;
      })
      .join("");
    const meta = `${dayMonth(dayOf(data.starts_at))}, ${clock(data.starts_at)} · ${data.group_name || ""} · ${t("pnlStudentsN", { n: students.length })}`;
    box.innerHTML = `<h2>${esc(meta)}</h2>
      ${future ? `<p class="pd-note">${esc(t("attFuture"))}</p>` : ""}
      ${students.length ? `<div class="pd-roll-tools">
          ${button(t("attAll"), `data-roll-all${future ? " disabled" : ""}`, "primary")}
          <span class="pn-muted">${esc(t("pdUnmarkedN", { n: left }))}</span>
        </div>
        <ul class="pd-roll" aria-label="${esc(t("pnlAttendance"))}">${lines}</ul>
        <div class="pd-actions">${button(t("save"), `data-roll-save${future ? " disabled" : ""}`, "primary")}</div>` : `${empty(t("attEmpty"))}<a class="pn-btn pn-btn-ghost" href="#/groups/${Number(data.group_id || row.group_id)}">${esc(t("pdAddToGroup"))}</a>`}`;
  };
  paint();
  box.onclick = (event) => {
    const node = event.target instanceof Element ? event.target.closest("button") : null;
    if (!node || node.disabled) return;
    if (node.hasAttribute("data-mark")) {
      const id = Number(node.getAttribute("data-student"));
      const status = node.getAttribute("data-mark");
      marks.set(id, marks.get(id) === status ? null : status);
      paint();
      const again = box.querySelector(`[data-student="${id}"][data-mark="${status}"]`);
      if (again) again.focus();
    } else if (node.hasAttribute("data-roll-all")) {
      (data.students || []).forEach((item) => marks.set(item.student_id, "present"));
      paint();
    } else if (node.hasAttribute("data-roll-save")) {
      busy(node, async () => {
        const body = { marks: (data.students || []).map((item) => ({ student_id: item.student_id, status: marks.get(item.student_id) || "" })) };
        data = await send(`/api/tutor/sessions/${row.id}/attendance`, "PUT", body);
        marks.clear();
        (data.students || []).forEach((item) => marks.set(item.student_id, item.status));
        toast(t("saved"));
        const marked = (data.students || []).some((item) => item.status);
        if (done) done(marked);
        else paint();
      });
    }
  };
}
