import {
  api, busy, button, chips, dayMonth, dialog, empty, esc, failed, field, head, input, loading, money, monthLabel,
  on, select, send, t, tag, toast, todayIso,
} from "./panel_kit.js";

/** To‘lovlar (invoices, payments, waive) and Hisobotlar (monthly numbers, CSV). */
const METHODS = [["cash", "feeCash"], ["card", "feeCard"], ["transfer", "feeTransfer"], ["other", "feeOther"]];
const fees = { filter: "", query: "" };

function late(row, today) {
  return row.status === "overdue" || (row.status === "due" && row.due_on && row.due_on < today);
}

function packageLeft(row) {
  return row.kind === "package" && row.lessons_total ? Math.max(0, row.lessons_total - (row.lessons_used || 0)) : null;
}

function stateTag(row, today) {
  if (row.status === "paid") return tag("ok", t("feePaid"));
  if (row.status === "waived") return tag("muted", t("pdWaived"));
  if (late(row, today)) return tag("bad", t("pdOverdueTag"));
  if (row.kind === "package") return tag("muted", t("feePackage"));
  return tag("warn", t("feeDueFilter"));
}

export async function renderFees(main, parts) {
  const title = t("pnlFees");
  if (parts[0]) fees.filter = parts[0] === "all" ? "" : parts[0];
  loading(main, title);
  let rows;
  let summary;
  let students;
  try {
    [rows, summary, students] = await Promise.all([
      api("/api/tutor/invoices"),
      api("/api/tutor/fees/summary"),
      api("/api/tutor/students").then((data) => data.students || []),
    ]);
  } catch (err) {
    failed(main, title, err);
    return;
  }
  const today = todayIso();
  const open = rows.filter((row) => row.status === "due" || row.status === "overdue");
  const lateRows = open.filter((row) => late(row, today));
  // Debt typed on a student card (no invoice yet) is part of the outstanding total, so list it too.
  const covered = new Set(open.map((row) => row.student_id));
  const cardDebts = students.filter((row) => row.status === "debtor" && row.amount_uzs > 0 && !covered.has(row.id));
  const debtors = new Set([...covered, ...cardDebts.map((row) => row.id)]).size;
  const ending = open.filter((row) => {
    const left = packageLeft(row);
    return left !== null && left <= 1;
  }).length;
  const paint = () => {
    const query = fees.query.trim().toLowerCase();
    const shown = rows.filter((row) => {
      if (fees.filter === "due" && !(row.status === "due" && !late(row, today))) return false;
      if (fees.filter === "overdue" && !late(row, today)) return false;
      if (fees.filter === "paid" && row.status !== "paid") return false;
      return !query || `${row.student_name} ${row.group_name}`.toLowerCase().includes(query);
    });
    const filters = [["", t("pdAll")], ["due", t("feeDueFilter")], ["overdue", t("pdOverdueTag")], ["paid", t("feePaid")]];
    const amount = (row) => {
      const left = packageLeft(row);
      if (left !== null) return t("pdLessonsLeft", { left, total: row.lessons_total });
      const due = row.amount_uzs - row.paid_uzs;
      return money(row.status === "paid" || row.status === "waived" || due <= 0 ? row.amount_uzs : due);
    };
    const act = (row) => (row.status === "due" || row.status === "overdue"
      ? `${button(t("pdRecord"), `data-pay="${row.id}"`, "primary")}${button(t("pdWaive"), `data-waive="${row.id}"`)}`
      : "");
    const table = shown
      .map((row) => `<tr>
        <td><a class="pd-strong" href="#/students/${row.student_id}">${esc(row.student_name || "")}</a></td>
        <td>${esc(row.group_name || "")}</td>
        <td class="pn-num">${esc(amount(row))}</td>
        <td class="pn-num">${esc(row.due_on ? dayMonth(row.due_on) : "—")}</td>
        <td>${stateTag(row, today)}</td>
        <td class="pn-act"><span class="pd-actions">${act(row)}</span></td>
      </tr>`)
      .join("");
    const showCards = (fees.filter === "" || fees.filter === "due") && cardDebts.filter(
      (row) => !query || row.name.toLowerCase().includes(query),
    );
    const cardRows = (showCards || [])
      .map((row) => `<tr>
        <td><a class="pd-strong" href="#/students/${row.id}">${esc(row.name)}</a></td>
        <td class="pn-muted">—</td>
        <td class="pn-num">${esc(money(row.amount_uzs))}</td>
        <td class="pn-num">—</td>
        <td>${tag("bad", t("pdCardDebt"))}</td>
        <td class="pn-act"><a class="pn-btn pn-btn-ghost pn-btn-sm" href="#/students/${row.id}">${esc(t("pdOpenCard"))}</a></td>
      </tr>`)
      .join("");
    const cardItems = (showCards || [])
      .map((row) => `<li class="pd-member pd-fee-card"><span class="pd-pick-text"><b>${esc(row.name)}</b>
        <small class="pn-num">${esc(money(row.amount_uzs))}</small></span>${tag("bad", t("pdCardDebt"))}
        <span class="pd-actions"><a class="pn-btn pn-btn-ghost pn-btn-sm" href="#/students/${row.id}">${esc(t("pdOpenCard"))}</a></span></li>`)
      .join("");
    const cards = shown
      .map((row) => `<li class="pd-member pd-fee-card"><span class="pd-pick-text"><b>${esc(row.student_name || "")}</b>
        <small>${esc(`${row.group_name || ""} · ${row.due_on ? dayMonth(row.due_on) : "—"}`)}</small><small class="pn-num">${esc(amount(row))}</small></span>
        ${stateTag(row, today)}<span class="pd-actions">${act(row)}</span></li>`)
      .join("");
    main.innerHTML = `${head(title, `${monthLabel(today.slice(0, 7))} · ${t("pdFeesLead")}`)}
      <section class="pn-kpis">
        ${kpi("pdDebtKpi", money(summary.outstanding_uzs), t("pdDebtors", { n: debtors }), "bad")}
        ${kpi("pnlOverdue", String(lateRows.length), t("pdOverdueSub"), "warn")}
        ${kpi("pdCollected", money(summary.collected_uzs), t("pnlIncomeTag"), "ok")}
        ${kpi("pdPackEnding", String(ending), t("pdPackEndingSub"), "accent")}
      </section>
      <div class="pd-toolbar">${chips(filters, fees.filter, "data-filter")}
        <input class="pd-input pd-search" type="search" id="pd-q" value="${esc(fees.query)}" placeholder="${esc(t("pdSearchFee"))}" aria-label="${esc(t("pdSearchFee"))}"></div>
      <section class="pn-card">${shown.length || cardRows ? `
        <div class="pn-table-wrap pn-only-wide"><table class="pn-table">
          <thead><tr><th scope="col">${esc(t("stuName"))}</th><th scope="col">${esc(t("pnlColGroup"))}</th><th scope="col">${esc(t("feeAmount"))}</th><th scope="col">${esc(t("pdDueOn"))}</th><th scope="col">${esc(t("stuStatus"))}</th><th scope="col"><span class="pn-sr">${esc(t("pnlColAction"))}</span></th></tr></thead>
          <tbody>${table}${cardRows}</tbody></table></div>
        <ul class="pd-members pn-only-phone">${cards}${cardItems}</ul>` : empty(t("feeEmpty"))}
        ${cardRows ? `<p class="pn-muted pd-small">${esc(t("pdCardDebtsHint"))}</p>` : ""}</section>`;
    const search = main.querySelector("#pd-q");
    search.addEventListener("input", () => {
      fees.query = search.value;
      const at = search.selectionStart;
      paint();
      const again = main.querySelector("#pd-q");
      again.focus();
      again.setSelectionRange(at, at);
    });
  };
  paint();
  on(main, "data-filter", (node) => {
    fees.filter = node.getAttribute("data-filter");
    paint();
  });
  on(main, "data-pay", (node) => payDialog(main, rows.find((row) => row.id === Number(node.getAttribute("data-pay")))));
  on(main, "data-waive", (node) => {
    if (!window.confirm(t("pdWaiveAsk"))) return;
    busy(node, async () => {
      await send(`/api/tutor/invoices/${Number(node.getAttribute("data-waive"))}/waive`, "POST", {});
      toast(t("saved"));
      renderFees(main, []);
    });
  });
}

function kpi(label, value, sub, tone) {
  return `<div class="pn-kpi pd-kpi-static"><span class="pn-kpi-label">${esc(t(label))}</span>
    <span class="pn-kpi-value pn-${tone}">${esc(value)}</span><span class="pn-kpi-sub">${esc(sub)}</span></div>`;
}

function payDialog(main, row) {
  if (!row) return;
  const left = Math.max(0, row.amount_uzs - row.paid_uzs);
  const fields = `
    <p class="pn-muted">${esc(`${row.student_name} · ${row.group_name} · ${t("pdLeft")}: ${money(left)}`)}</p>
    ${field(t("feeAmount"), input("amount_uzs", left, 'type="number" min="1" step="1000" inputmode="numeric" required'))}
    <div class="pd-row2">
      ${field(t("feeDate"), input("paid_on", todayIso(), 'type="date" required'))}
      ${field(t("pdMethod"), select("method", METHODS.map(([v, k]) => [v, t(k)]), "cash"))}
    </div>`;
  dialog(t("pdRecord"), fields, async (form) => {
    const data = new FormData(form);
    const amount = Number(data.get("amount_uzs") || 0);
    if (!Number.isInteger(amount) || amount <= 0) throw Object.assign(new Error("amount"), { code: "amount" });
    await send(`/api/tutor/invoices/${row.id}/payments`, "POST", { amount_uzs: amount, paid_on: data.get("paid_on"), method: data.get("method") });
    toast(t("saved"));
    renderFees(main, []);
  });
}

/* ---------- Hisobotlar ---------- */

let reportMonth = "";

function shiftMonth(month, step) {
  const [y, m] = month.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1 + step, 1));
  return date.toISOString().slice(0, 7);
}

export async function renderReports(main) {
  const title = t("pnlReports");
  if (!reportMonth) reportMonth = todayIso().slice(0, 7);
  loading(main, title);
  let data = null;
  let locked = false;
  let summary = null;
  try {
    summary = await api("/api/tutor/fees/summary").catch(() => null);
    data = await api(`/api/tutor/reports/monthly?month=${reportMonth}`);
  } catch (err) {
    if (err.code !== "export") {
      failed(main, title, err);
      return;
    }
    locked = true;
  }
  const nav = `<div class="pd-weeknav">
    <button type="button" class="pn-icon-btn" data-month="-1" aria-label="${esc(t("pdPrevMonth"))}">‹</button>
    <span class="pd-strong">${esc(monthLabel(reportMonth))}</span>
    <button type="button" class="pn-icon-btn" data-month="1" aria-label="${esc(t("pdNextMonth"))}"${reportMonth >= todayIso().slice(0, 7) ? " disabled" : ""}>›</button></div>`;
  const exports = `<section class="pn-card"><h2>${esc(t("pdExports"))}</h2><div class="pd-actions">
    <a class="pn-btn pn-btn-ghost" href="/api/tutor/export/students.csv" download>${esc(t("expStudents"))}</a>
    <a class="pn-btn pn-btn-ghost" href="/api/tutor/export/payments.csv?month=${reportMonth}" download>${esc(t("expPayments"))}</a></div>
    <p class="pn-muted pd-small">${esc(t("pdCsvHint"))}</p></section>`;
  if (locked) {
    main.innerHTML = `${head(title, t("pdReportsLead"))}${nav}
      <section class="pn-card pd-gap"><h2>${esc(t("pdLocked"))}</h2><p>${esc(t("limitExport"))}</p>
      <a class="pn-btn pn-btn-primary" href="#/settings/plan">${esc(t("pdSeePlan"))}</a></section>`;
  } else {
    const groups = data.groups || [];
    const rate = (value) => (value == null ? t("pdNoMarks") : `${Math.round(value * 100)}%`);
    const total = (key) => groups.reduce((sum, group) => sum + (Number(group[key]) || 0), 0);
    const rows = groups
      .map((group) => `<tr><td class="pd-strong">${esc(group.name || "")}</td><td class="pn-num">${esc(rate(group.attendance_rate))}</td>
        <td class="pn-num">${esc(money(group.collected_uzs))}</td><td class="pn-num">${esc(money(group.outstanding_uzs))}</td>
        <td class="pn-act"><a class="pn-btn pn-btn-ghost pn-btn-sm" href="/api/tutor/export/attendance.csv?group_id=${Number(group.group_id)}&amp;month=${reportMonth}" download>CSV</a></td></tr>`)
      .join("");
    main.innerHTML = `${head(title, t("pdReportsLead"))}${nav}
      <section class="pn-kpis">
        ${kpi("pdCollected", money(total("collected_uzs")), monthLabel(reportMonth), "ok")}
        ${kpi("pdMonthDebt", money(total("outstanding_uzs")), t("pdMonthDebtSub"), "warn")}
        ${kpi("pdTotalDebt", summary ? money(summary.outstanding_uzs) : "—", t("pdTotalDebtSub"), "bad")}
        ${kpi("pdNewStudents", `${data.new_students || 0} / ${data.left_students || 0}`, t("pdNewLeftSub"), "accent")}
      </section>
      <section class="pn-card pd-gap">${groups.length ? `<div class="pn-table-wrap"><table class="pn-table">
        <thead><tr><th scope="col">${esc(t("pnlColGroup"))}</th><th scope="col">${esc(t("pnlAttendance"))}</th><th scope="col">${esc(t("pdCollected"))}</th><th scope="col">${esc(t("pdMonthDebt"))}</th><th scope="col"><span class="pn-sr">CSV</span></th></tr></thead>
        <tbody>${rows}</tbody></table></div>` : empty(t("repNone"))}</section>${exports}`;
  }
  on(main, "data-month", (node) => {
    reportMonth = shiftMonth(reportMonth, Number(node.getAttribute("data-month")));
    renderReports(main);
  });
}
