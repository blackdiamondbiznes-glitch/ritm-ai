import {
  api, busy, button, chips, dayToggles, daysText, dialog, empty, esc, failed, field, groupLabel, head, input,
  inviteLink, loading, money, on, select, send, t, tag, toast, todayIso,
} from "./panel_kit.js";

/** Guruhlar and O‘quvchilar pages, on the existing /api/tutor/* endpoints. */
const STATUS = {
  paid: ["ok", "stuPaid"],
  debtor: ["bad", "stuDebtor"],
  inactive: ["muted", "stuInactive"],
  pending: ["warn", "pdStuPending"],
};
const LESSON_MIN = [["", "noticeOff"], ["15", "noticeMin15"], ["30", "noticeMin30"], ["60", "noticeMin60"], ["120", "noticeMin120"]];
const FEE_DAYS = [["", "noticeOff"], ["1", "noticeDay1"], ["3", "noticeDay3"], ["7", "noticeDay7"]];
const MODES = [["none", "feeNone"], ["monthly", "feeMonthly"], ["package", "feePackage"]];

function statusTag(status) {
  const [tone, key] = STATUS[status] || STATUS.inactive;
  return tag(tone, t(key));
}

function feeText(group) {
  if (group.fee_mode === "monthly") return `${t("feeMonthly")} · ${money(group.fee_uzs)}`;
  if (group.fee_mode === "package") return `${t("feePackage")} · ${group.package_lessons || 0} · ${money(group.fee_uzs)}`;
  return t("feeNone");
}

function timeText(group) {
  return `${daysText(group.weekdays)} · ${group.start}–${group.end}`;
}

/* ---------- Guruhlar ---------- */

export async function renderGroups(main, parts) {
  if (parts[0]) return renderGroup(main, Number(parts[0]));
  const title = t("pnlGroups");
  loading(main, title);
  let groups;
  try {
    groups = (await api("/api/tutor/groups")).groups || [];
  } catch (err) {
    failed(main, title, err);
    return;
  }
  const add = button(t("pdAddGroup"), "data-add-group", "primary", "plus");
  const rows = groups
    .map((group) => `<tr>
      <td><a class="pd-strong" href="#/groups/${group.id}">${esc(groupLabel(group))}</a></td>
      <td class="pn-num">${esc(timeText(group))}</td>
      <td class="pn-num">${esc(group.students)}</td>
      <td>${esc(feeText(group))}</td>
      <td class="pn-num">${esc(group.enroll_code || "")}</td>
      <td class="pn-act"><a class="pn-btn pn-btn-ghost pn-btn-sm" href="#/groups/${group.id}">${esc(t("pdOpen"))}</a></td>
    </tr>`)
    .join("");
  const cards = groups
    .map((group) => `<li><a class="pd-pick" href="#/groups/${group.id}">
      <span class="pd-pick-text"><b>${esc(groupLabel(group))}</b><small>${esc(timeText(group))}</small><small>${esc(feeText(group))}</small></span>
      <span class="pd-count">${esc(t("pnlStudentsN", { n: group.students }))}</span></a></li>`)
    .join("");
  main.innerHTML = `${head(title, t("pdGroupsLead", { n: groups.length }), add)}
    <section class="pn-card">${groups.length ? `
      <div class="pn-table-wrap pn-only-wide"><table class="pn-table">
        <thead><tr><th scope="col">${esc(t("pnlColGroup"))}</th><th scope="col">${esc(t("pdColDays"))}</th><th scope="col">${esc(t("pnlColStudents"))}</th><th scope="col">${esc(t("pdColFee"))}</th><th scope="col">${esc(t("pdColCode"))}</th><th scope="col"><span class="pn-sr">${esc(t("pnlColAction"))}</span></th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      <ul class="pd-pick-list pn-only-phone">${cards}</ul>` : empty(t("grpEmpty"))}
    </section>`;
  on(main, "data-add-group", () => groupDialog(main, null));
}

function groupDialog(main, group) {
  const fields = `
    <div class="pd-row2">
      ${field(t("grpName"), input("name", group ? group.name : "", 'maxlength="80" required'))}
      ${field(t("grpLevel"), input("level", group ? group.level || "" : "", 'maxlength="40"'))}
    </div>
    ${field(t("pdColDays"), dayToggles(group ? group.weekdays : [1, 3, 5]))}
    <div class="pd-row2">
      ${field(t("pdStart"), input("start", group ? group.start : "18:00", 'type="time" required'))}
      ${field(t("pdEnd"), input("end", group ? group.end : "19:30", 'type="time" required'))}
    </div>`;
  dialog(group ? t("pdEditGroup") : t("pdAddGroup"), fields, async (form) => {
    const data = new FormData(form);
    const body = {
      name: data.get("name"),
      level: data.get("level"),
      weekdays: data.getAll("weekdays").map(Number),
      start: data.get("start"),
      end: data.get("end"),
    };
    const saved = await send(group ? `/api/tutor/groups/${group.id}` : "/api/tutor/groups", group ? "PATCH" : "POST", body);
    toast(t("saved"));
    const fresh = saved && saved.group ? saved.group : (saved.groups || []).find((row) => row.name === body.name);
    if (fresh && fresh.id) location.hash = `#/groups/${fresh.id}`;
    else renderGroups(main, group ? [String(group.id)] : []);
  });
}

async function renderGroup(main, id) {
  const title = t("pnlGroups");
  loading(main, title);
  let data;
  let notify;
  try {
    [data, notify] = await Promise.all([api(`/api/tutor/groups/${id}`), api(`/api/tutor/groups/${id}/notify`)]);
  } catch (err) {
    failed(main, title, err);
    return;
  }
  const group = data.group;
  const link = inviteLink(group.enroll_code);
  const month = todayIso().slice(0, 7);
  const members = (data.members || [])
    .map((row) => `<li class="pd-member"><a class="pd-strong" href="#/students/${row.id}">${esc(row.name)}</a>${statusTag(row.status)}
      <button type="button" class="pn-btn pn-btn-ghost pn-btn-sm" data-remove="${row.id}" aria-label="${esc(`${t("pdRemove")}: ${row.name}`)}">${esc(t("pdRemove"))}</button></li>`)
    .join("");
  const available = data.available || [];
  const chatOptions = [["", t("noticeChatNone")], ...(notify.chats || []).map((chat) => [chat.id, chat.title || ""])];
  const actions = `<a class="pn-btn pn-btn-ghost" href="#/groups">${esc(t("pdBack"))}</a>${button(t("pdEdit"), "data-edit-group", "primary")}`;
  main.innerHTML = `${head(groupLabel(group), timeText(group), actions)}
    <div class="pd-split">
      <section class="pn-card">
        <h2>${esc(t("pnlStudents"))} · ${esc(String((data.members || []).length))}</h2>
        ${members ? `<ul class="pd-members">${members}</ul>` : empty(t("attEmpty"))}
        <form class="pd-form pd-inline-form" id="pd-add-member" novalidate>
          ${available.length ? `<div class="pd-row-act">${field(t("pdAddExisting"), select("student_id", available.map((row) => [row.id, row.name]), ""))}<button type="submit" class="pn-btn pn-btn-ghost" name="mode" value="old">${esc(t("pdAdd"))}</button></div>` : ""}
          <div class="pd-row-act">${field(t("pdAddNew"), input("name", "", `maxlength="80" placeholder="${esc(t("stuName"))}"`))}<button type="submit" class="pn-btn pn-btn-primary" name="mode" value="new">${esc(t("pdAdd"))}</button></div>
        </form>
      </section>
      <aside class="pd-stack">
        <section class="pn-card">
          <h2>${esc(t("grpLinkTitle"))}</h2>
          <p class="pd-big pn-num">${esc(group.enroll_code || "—")}</p>
          ${link ? `<p class="pd-wrap"><a class="pn-link" href="${esc(link)}" target="_blank" rel="noopener noreferrer">${esc(link)}</a></p>${button(t("grpLinkCopy"), `data-copy="${esc(link)}"`)}` : ""}
          <p class="pn-muted pd-small">${esc(t("grpLinkLead"))}</p>
        </section>
        <section class="pn-card">
          <h2>${esc(t("pdColFee"))}</h2>
          <p class="pd-line">${esc(feeText(group))}</p>
          ${group.fee_mode === "monthly" ? `<p class="pn-muted pd-small">${esc(`${t("feeDay")}: ${group.billing_day ?? "—"} · ${t("feeDue")}: ${group.due_days ?? "—"}`)}</p>` : ""}
          ${button(t("pdEditFee"), "data-edit-fee")}
        </section>
        <section class="pn-card">
          <h2>${esc(t("pdReminders"))}</h2>
          <form class="pd-form" id="pd-notify" novalidate>
            ${field(t("noticeLesson"), select("lesson", LESSON_MIN.map(([v, k]) => [v, t(k)]), notify.remind_lesson_min ?? ""))}
            ${field(t("noticeFee"), select("fee", FEE_DAYS.map(([v, k]) => [v, t(k)]), notify.remind_fee_days ?? ""))}
            ${field(t("noticeChat"), select("chat", chatOptions, notify.chat_id ?? ""))}
            <label class="pd-check"><input type="checkbox" name="fee_in_group"${notify.fee_in_group ? " checked" : ""}><span>${esc(t("noticeFeeGroup"))}</span></label>
            <button type="submit" class="pn-btn pn-btn-primary">${esc(t("save"))}</button>
          </form>
        </section>
        <section class="pn-card">
          <h2>${esc(t("noticeAnnounce"))}</h2>
          <form class="pd-form" id="pd-announce" novalidate>
            ${field(t("noticeText"), `<textarea class="pd-input" name="text" rows="3" maxlength="1000" required></textarea>`)}
            <label class="pd-check"><input type="checkbox" name="to_students" checked><span>${esc(t("noticeToStudents"))}</span></label>
            <label class="pd-check"><input type="checkbox" name="to_chat"${notify.chat_id ? " checked" : " disabled"}><span>${esc(t("noticeToChat"))}</span></label>
            <button type="submit" class="pn-btn pn-btn-primary">${esc(t("pdSend"))}</button>
          </form>
        </section>
        <section class="pn-card">
          <h2>${esc(t("pnlReports"))}</h2>
          <a class="pn-btn pn-btn-ghost" href="/api/tutor/export/attendance.csv?group_id=${group.id}&amp;month=${month}" download>${esc(t("pdAttCsv"))}</a>
        </section>
      </aside>
    </div>`;
  on(main, "data-edit-group", () => groupDialog(main, group));
  on(main, "data-edit-fee", () => feeDialog(main, group));
  on(main, "data-copy", (node) => {
    navigator.clipboard.writeText(node.getAttribute("data-copy")).then(() => toast(t("pdCopied")), () => toast(t("error"), "err"));
  });
  on(main, "data-remove", (node) => {
    if (!window.confirm(t("pdRemoveAsk"))) return;
    busy(node, async () => {
      await api(`/api/tutor/groups/${group.id}/students/${Number(node.getAttribute("data-remove"))}`, { method: "DELETE" });
      toast(t("saved"));
      renderGroup(main, group.id);
    });
  });
  const addForm = main.querySelector("#pd-add-member");
  addForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const mode = event.submitter ? event.submitter.value : "new";
    const data = new FormData(addForm);
    busy(event.submitter, async () => {
      if (mode === "old") {
        await send(`/api/tutor/groups/${group.id}/students`, "POST", { student_id: Number(data.get("student_id")) });
      } else {
        const name = String(data.get("name") || "").trim();
        if (!name) throw Object.assign(new Error("empty"), { code: "empty" });
        await send("/api/tutor/students", "POST", { name, status: "paid", amount_uzs: 0, group_ids: [group.id] });
      }
      toast(t("saved"));
      renderGroup(main, group.id);
    });
  });
  const notifyForm = main.querySelector("#pd-notify");
  notifyForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(notifyForm);
    busy(notifyForm.querySelector('[type="submit"]'), async () => {
      const lesson = data.get("lesson");
      const fee = data.get("fee");
      await send(`/api/tutor/groups/${group.id}/notify`, "PUT", {
        remind_lesson_min: lesson ? Number(lesson) : null,
        remind_fee_days: fee ? Number(fee) : null,
        fee_in_group: data.get("fee_in_group") === "on",
      });
      const chat = data.get("chat");
      if (String(chat || "") !== String(notify.chat_id ?? "")) {
        await send(`/api/tutor/groups/${group.id}/chat`, "PUT", { chat_id: chat ? Number(chat) : null });
      }
      toast(t("saved"));
    });
  });
  const announce = main.querySelector("#pd-announce");
  announce.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(announce);
    busy(announce.querySelector('[type="submit"]'), async () => {
      await send(`/api/tutor/groups/${group.id}/announce`, "POST", {
        text: data.get("text"),
        to_chat: data.get("to_chat") === "on",
        to_students: data.get("to_students") === "on",
      });
      announce.reset();
      toast(t("noticeSent"));
    });
  });
}

function feeDialog(main, group) {
  const fields = `
    ${field(t("pdColFee"), select("fee_mode", MODES.map(([v, k]) => [v, t(k)]), group.fee_mode || "none"))}
    ${field(t("feeAmount"), input("fee_uzs", group.fee_uzs || 0, 'type="number" min="0" step="1000" inputmode="numeric"'))}
    <div class="pd-row2">
      ${field(t("feeDay"), input("billing_day", group.billing_day || 1, 'type="number" min="1" max="28" inputmode="numeric"'))}
      ${field(t("feeDue"), input("due_days", group.due_days ?? 5, 'type="number" min="0" max="60" inputmode="numeric"'))}
    </div>
    ${field(t("feeSize"), input("package_lessons", group.package_lessons || 8, 'type="number" min="1" max="200" inputmode="numeric"'), t("feeSizeHelp"))}`;
  dialog(t("pdEditFee"), fields, async (form) => {
    const data = new FormData(form);
    const mode = String(data.get("fee_mode"));
    await send(`/api/tutor/groups/${group.id}/fee`, "PUT", {
      fee_mode: mode,
      fee_uzs: Number(data.get("fee_uzs") || 0),
      due_days: Number(data.get("due_days") || 0),
      billing_day: mode === "monthly" ? Number(data.get("billing_day")) : null,
      package_lessons: mode === "package" ? Number(data.get("package_lessons")) : null,
    });
    toast(t("saved"));
    renderGroup(main, group.id);
  });
}

/* ---------- O‘quvchilar ---------- */

const people = { filter: "", query: "" };

export async function renderStudents(main, parts) {
  if (parts[0] && parts[0] !== "requests") return renderStudent(main, Number(parts[0]));
  const title = t("pnlStudents");
  loading(main, title);
  let list;
  let requests;
  let groups;
  try {
    [list, requests, groups] = await Promise.all([
      api("/api/tutor/students"),
      api("/api/tutor/requests").then((data) => data.requests || []),
      api("/api/tutor/groups").then((data) => data.groups || []),
    ]);
  } catch (err) {
    failed(main, title, err);
    return;
  }
  const counts = list.counts || {};
  const paint = () => {
    const query = people.query.trim().toLowerCase();
    const rows = (list.students || []).filter(
      (row) => (!people.filter || row.status === people.filter) && (!query || `${row.name} ${row.phone || ""}`.toLowerCase().includes(query)),
    );
    const filters = [
      ["", t("pdAll")],
      ["paid", `${t("stuPaid")} · ${counts.paid || 0}`],
      ["debtor", `${t("stuDebtor")} · ${counts.debtor || 0}`],
      ["inactive", `${t("stuInactive")} · ${counts.inactive || 0}`],
    ];
    const table = rows
      .map((row) => `<tr>
        <td><a class="pd-strong" href="#/students/${row.id}">${esc(row.name)}</a></td>
        <td class="pn-num">${esc(row.phone || "—")}</td>
        <td>${statusTag(row.status)}</td>
        <td class="pn-num">${row.status === "debtor" ? esc(money(row.amount_uzs)) : "—"}</td>
        <td class="pn-act"><a class="pn-btn pn-btn-ghost pn-btn-sm" href="#/students/${row.id}">${esc(t("pdOpen"))}</a></td>
      </tr>`)
      .join("");
    const cards = rows
      .map((row) => `<li><a class="pd-pick" href="#/students/${row.id}">
        <span class="pd-pick-text"><b>${esc(row.name)}</b><small>${esc(row.phone || "")}</small></span>${statusTag(row.status)}</a></li>`)
      .join("");
    const asks = requests
      .map((row) => `<li class="pd-member"><span class="pd-pick-text"><b>${esc(row.name)}</b><small>${esc(row.group_name)}</small></span>
        <span class="pd-actions">${button(t("reqApprove"), `data-decide="approve" data-g="${row.group_id}" data-s="${row.student_id}"`, "primary")}
        ${button(t("reqReject"), `data-decide="reject" data-g="${row.group_id}" data-s="${row.student_id}"`)}</span></li>`)
      .join("");
    main.innerHTML = `${head(title, t("pdStudentsLead", { n: (list.students || []).length }), button(t("pdAddStudent"), "data-add-student", "primary", "plus"))}
      ${requests.length ? `<section class="pn-card pd-gap" id="pd-requests"><h2>${esc(t("reqTitle", { n: requests.length }))}</h2><ul class="pd-members">${asks}</ul></section>` : ""}
      <div class="pd-toolbar">${chips(filters, people.filter, "data-filter")}
        <input class="pd-input pd-search" type="search" id="pd-q" value="${esc(people.query)}" placeholder="${esc(t("pdSearchStudent"))}" aria-label="${esc(t("pdSearchStudent"))}"></div>
      <section class="pn-card">${rows.length ? `
        <div class="pn-table-wrap pn-only-wide"><table class="pn-table">
          <thead><tr><th scope="col">${esc(t("stuName"))}</th><th scope="col">${esc(t("stuPhone"))}</th><th scope="col">${esc(t("stuStatus"))}</th><th scope="col">${esc(t("pdDebt"))}</th><th scope="col"><span class="pn-sr">${esc(t("pnlColAction"))}</span></th></tr></thead>
          <tbody>${table}</tbody></table></div>
        <ul class="pd-pick-list pn-only-phone">${cards}</ul>` : empty(t("stuEmpty"))}</section>`;
    const search = main.querySelector("#pd-q");
    search.addEventListener("input", () => {
      people.query = search.value;
      const at = search.selectionStart;
      paint();
      const again = main.querySelector("#pd-q");
      again.focus();
      again.setSelectionRange(at, at);
    });
  };
  paint();
  if (parts[0] === "requests") {
    const box = main.querySelector("#pd-requests");
    if (box) box.scrollIntoView({ block: "start" });
  }
  on(main, "data-filter", (node) => {
    people.filter = node.getAttribute("data-filter");
    paint();
  });
  on(main, "data-add-student", () => studentDialog(main, null, groups, []));
  on(main, "data-decide", (node) =>
    busy(node, async () => {
      await send(`/api/tutor/requests/${Number(node.getAttribute("data-g"))}/${Number(node.getAttribute("data-s"))}/${node.getAttribute("data-decide")}`, "POST", {});
      toast(t("saved"));
      renderStudents(main, []);
    }),
  );
}

function studentDialog(main, row, groups, chosen) {
  const statusOptions = ["paid", "debtor", "inactive"].map((value) => [value, t(STATUS[value][1])]);
  const groupBoxes = groups
    .map((group) => `<label class="pd-check"><input type="checkbox" name="group_ids" value="${group.id}"${chosen.includes(group.id) ? " checked" : ""}><span>${esc(groupLabel(group))}</span></label>`)
    .join("");
  const fields = `
    ${field(t("stuName"), input("name", row ? row.name : "", 'maxlength="80" required'))}
    <div class="pd-row2">
      ${field(t("stuPhone"), input("phone", row ? row.phone || "" : "", 'type="tel" maxlength="32" inputmode="tel"'))}
      ${field(t("stuStatus"), select("status", statusOptions, row ? row.status : "paid"))}
    </div>
    ${field(t("pdDebt"), input("amount_uzs", row ? row.amount_uzs || 0 : 0, 'type="number" min="0" step="1000" inputmode="numeric"'), t("pdDebtHint"))}
    ${field(t("stuNote"), `<textarea class="pd-input" name="note" rows="2" maxlength="300">${esc(row ? row.note || "" : "")}</textarea>`)}
    ${groups.length ? `<fieldset class="pd-fieldset"><legend class="pd-label">${esc(t("pnlGroups"))}</legend>${groupBoxes}</fieldset>` : ""}`;
  dialog(row ? t("pdEditStudent") : t("pdAddStudent"), fields, async (form) => {
    const data = new FormData(form);
    const status = String(data.get("status"));
    const body = {
      name: data.get("name"),
      phone: data.get("phone"),
      status,
      amount_uzs: status === "debtor" ? Number(data.get("amount_uzs") || 0) : 0,
      note: data.get("note"),
      group_ids: data.getAll("group_ids").map(Number),
    };
    if (groups.length && !body.group_ids.length) throw Object.assign(new Error("groups"), { code: "pd_group_need" });
    await send(row ? `/api/tutor/students/${row.id}` : "/api/tutor/students", row ? "PATCH" : "POST", body);
    toast(t("saved"));
    if (row) renderStudent(main, row.id);
    else renderStudents(main, []);
  });
}

async function renderStudent(main, id) {
  const title = t("pnlStudents");
  loading(main, title);
  let data;
  let groups;
  try {
    [data, groups] = await Promise.all([api(`/api/tutor/students/${id}`), api("/api/tutor/groups").then((body) => body.groups || [])]);
  } catch (err) {
    failed(main, title, err);
    return;
  }
  const row = data.student;
  const chosen = (data.groups || []).map((group) => group.id);
  const lessons = (data.lessons || [])
    .slice(0, 12)
    .map((lesson) => `<li class="pd-member"><span class="pd-pick-text"><b>${esc(lesson.title || "")}</b><small>${esc(String(lesson.starts_at || "").slice(0, 10))}</small></span></li>`)
    .join("");
  const actions = `<a class="pn-btn pn-btn-ghost" href="#/students">${esc(t("pdBack"))}</a>${button(t("pdEdit"), "data-edit-student", "primary")}`;
  main.innerHTML = `${head(row.name, row.phone || "", actions)}
    <div class="pd-split">
      <section class="pn-card">
        <h2>${esc(t("pdCard"))}</h2>
        <dl class="pd-dl">
          <dt>${esc(t("stuStatus"))}</dt><dd>${statusTag(row.status)}</dd>
          <dt>${esc(t("pdDebt"))}</dt><dd class="pn-num">${row.status === "debtor" ? esc(money(row.amount_uzs)) : "—"}</dd>
          <dt>${esc(t("stuPhone"))}</dt><dd>${esc(row.phone || "—")}</dd>
          <dt>${esc(t("stuNote"))}</dt><dd>${esc(row.note || "—")}</dd>
          <dt>${esc(t("pdJoinCode"))}</dt><dd class="pn-num">${esc(row.join_code || "—")}</dd>
        </dl>
        <h2 class="pd-gap-top">${esc(t("pnlGroups"))}</h2>
        ${(data.groups || []).length ? `<ul class="pd-members">${data.groups.map((group) => `<li class="pd-member"><a class="pd-strong" href="#/groups/${group.id}">${esc(group.name)}</a></li>`).join("")}</ul>` : empty(t("pdNoGroups"))}
      </section>
      <aside class="pn-card">
        <h2>${esc(t("pdSoloLessons"))}</h2>
        ${lessons ? `<ul class="pd-members">${lessons}</ul>` : empty(t("pdNoSolo"))}
        <a class="pn-btn pn-btn-ghost" href="#/fees">${esc(t("pnlFees"))}</a>
      </aside>
    </div>`;
  on(main, "data-edit-student", () => studentDialog(main, row, groups, chosen));
}
