import { currentLang, dayLabel, t } from "./i18n.js";
import { escapeHtml } from "./html.js";

export function brandHeader() {
  return `<div class="header brand"><h1>🤖 Ritm AI</h1><p>${escapeHtml(t("tagline"))}</p></div>`;
}

export function chatCard(chat, attrs = "") {
  const title = escapeHtml(chat.title || "Chat");
  const facts = [];
  if (chat.member_count != null) facts.push(t("members", { n: chat.member_count }));
  if (chat.posts_total != null) facts.push(t("postsTotal", { n: chat.posts_total }));
  if (chat.quizzes_total != null) facts.push(t("quizzesTotal", { n: chat.quizzes_total }));
  const factHtml = facts.length
    ? `<div class="chat-facts">${facts.map((item) => `<span class="fact">${escapeHtml(item)}</span>`).join("")}</div>`
    : "";
  const plan = chat.plan_name ? `<span class="chat-plan">${escapeHtml(chat.plan_name)}</span>` : "";
  const badge = chat.role === "admin" || chat.role === "owner" ? roleBadge(chat.role) : "";
  return `<button type="button" class="chat-card list-btn" ${attrs}>
    <div class="row space"><div class="chat-name">${title}</div><div class="chat-tags">${badge}${plan}</div></div>
    <div class="chat-status">${escapeHtml(t("statusOn"))}</div>
    ${factHtml}
  </button>`;
}

export function roleBadge(role) {
  const key = role === "owner" ? "badgeOwner" : role === "admin" ? "badgeAdmin" : role === "super" ? "badgeSuper" : "badgeMember";
  return `<span class="role-badge role-${escapeHtml(role)}">${escapeHtml(t(key))}</span>`;
}

export function kpiRow(stats) {
  const week = stats && stats.week_counts;
  if (!week) return "";
  const items = [
    ["participants", "👥", "kpiActive"],
    ["posts", "📝", "kpiPosts"],
    ["answers", "🏆", "kpiAnswers"],
  ];
  const cells = items
    .map(([field, icon, label]) => {
      const item = week[field];
      if (!item || item.value == null) return "";
      const change = item.change_pct;
      const growth =
        change != null
          ? `<div class="kpi-change${change < 0 ? " down" : ""}">${change > 0 ? "+" : ""}${change}%</div>`
          : "";
      return `<div class="kpi"><div class="kpi-icon">${icon}</div>
        <div class="kpi-value">${escapeHtml(formatNumber(item.value))}</div>
        <div class="kpi-label">${escapeHtml(t(label))}</div>${growth}</div>`;
    })
    .join("");
  if (!cells) return "";
  return `<div class="kpis">${cells}</div><div class="kpi-hint">${escapeHtml(t("kpiHint"))}</div>`;
}

export function formatNumber(value) {
  return String(Math.round(Number(value) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

const SERIES = [
  ["answers", "var(--accent)"],
  ["posts", "var(--header-1)"],
  ["quizzes", "var(--success)"],
];

export function sparkChart(daily) {
  if (!Array.isArray(daily) || !daily.length) return "";
  const width = 300;
  const height = 96;
  const pad = 8;
  let max = 0;
  daily.forEach((row) => SERIES.forEach(([key]) => (max = Math.max(max, Number(row[key]) || 0))));
  const step = daily.length > 1 ? (width - pad * 2) / (daily.length - 1) : 0;
  const y = (value) => height - pad - (max > 0 ? ((Number(value) || 0) / max) * (height - pad * 2) : 0);
  const lines = SERIES.map(([key, color]) => {
    const points = daily.map((row, i) => `${(pad + i * step).toFixed(1)},${y(row[key]).toFixed(1)}`).join(" ");
    const dots = daily
      .map((row, i) => `<circle cx="${(pad + i * step).toFixed(1)}" cy="${y(row[key]).toFixed(1)}" r="2.5" fill="${color}" />`)
      .join("");
    return `<polyline points="${points}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />${dots}`;
  }).join("");
  const labels = daily
    .map((row) => {
      const date = new Date(`${row.date}T12:00:00`);
      const iso = ((date.getDay() + 6) % 7) + 1;
      return `<span>${escapeHtml(dayLabel(iso))}</span>`;
    })
    .join("");
  const legend = SERIES.map(([key, color]) => {
    const total = daily.reduce((sum, row) => sum + (Number(row[key]) || 0), 0);
    return `<span class="legend-item"><i style="background:${color}"></i>${escapeHtml(t(key))}: <strong>${total}</strong></span>`;
  }).join("");
  const empty = max === 0 ? `<p class="muted">${escapeHtml(t("chartEmpty"))}</p>` : "";
  return `<div class="card chart-card">
    <div class="card-title">📈 ${escapeHtml(t("last7"))}</div>
    <svg class="spark" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(t("last7"))}">${lines}</svg>
    <div class="spark-days">${labels}</div>
    <div class="legend">${legend}</div>
    ${empty}
  </div>`;
}

export function metricGrid(counts) {
  if (!counts) return "";
  const keys = [
    ["posts", "posts"],
    ["quizzes", "quizzes"],
    ["answers", "answers"],
    ["participants", "participants"],
  ];
  const cells = keys
    .map(([field, label]) => {
      const item = counts[field];
      if (!item || item.value == null) return "";
      const change = item.change_pct;
      let growth = "";
      if (change != null) {
        const sign = change > 0 ? "+" : "";
        const cls = change < 0 ? "growth down" : "growth";
        growth = `<div class="${cls}">${sign}${change}%</div>`;
      }
      return `<div class="metric"><div class="label">${escapeHtml(t(label))}</div>
        <div class="big">${escapeHtml(String(item.value))}</div>${growth}</div>`;
    })
    .join("");
  return cells ? `<div class="metrics">${cells}</div>` : "";
}

export function statsCards(stats) {
  if (!stats) return "";
  const week = metricGrid(stats.week_counts);
  const today = metricGrid(stats.today_counts);
  let html = "";
  if (week) html += `<div class="card"><div class="card-title">${escapeHtml(t("weekStats"))}</div>${week}</div>`;
  if (today) html += `<div class="card"><div class="card-title">${escapeHtml(t("todayStats"))}</div>${today}</div>`;
  return html;
}

export function normalizeTime(value) {
  const text = String(value || "09:00");
  const match = text.match(/^(\d{1,2}):(\d{2})/);
  if (!match) return "09:00";
  return `${String(match[1]).padStart(2, "0")}:${match[2]}`;
}

export function section(icon, title, body, extraClass = "") {
  return `<section class="card section ${extraClass}">
    <header class="section-head"><span class="section-icon">${icon}</span><h2>${escapeHtml(title)}</h2></header>
    ${body}
  </section>`;
}

export function scheduleBlock(prefix, _title, row, withToggle) {
  const time = normalizeTime(row.time || "09:00");
  const preset = TIMES.includes(time);
  const chips = TIMES.map((item) => {
    const selected = item === time ? " selected" : "";
    return `<button type="button" class="chip-btn${selected}" data-value="${item}">${item}</button>`;
  }).join("");
  const custom = preset ? "" : time;
  return `<div class="field">
    <span class="field-label">${escapeHtml(t("time"))}</span>
    <div class="time-now">
      <span class="time-big" id="${prefix}_time_show">${time} ⏰</span>
      <button type="button" class="ghost small" data-time-toggle="${prefix}_time">${escapeHtml(t("change"))}</button>
    </div>
    <div class="time-edit" id="${prefix}_time_edit" hidden>
      <div class="chips" data-chip-target="${prefix}_time">${chips}</div>
      <label class="custom-time">${escapeHtml(t("customTime"))}
        <input type="time" id="${prefix}_time_custom" value="${custom}" />
      </label>
    </div>
    <input type="hidden" id="${prefix}_time" value="${time}" />
    ${withToggle ? toggleField(`${prefix}_enabled`, row.enabled, t("scheduleOn"), t("scheduleOff")) : ""}
  </div>`;
}

export function weekdayChips(current) {
  const selected = Number(current) || 1;
  const chips = [1, 2, 3, 4, 5, 6, 7]
    .map((day) => {
      const on = day === selected ? " selected" : "";
      return `<button type="button" class="chip-btn${on}" data-value="${day}">${escapeHtml(dayLabel(day))}</button>`;
    })
    .join("");
  return `<div class="field">
    <span class="field-label">${escapeHtml(t("weekday"))}</span>
    <div class="chips days" data-chip-target="board_weekday">${chips}</div>
    <input type="hidden" id="board_weekday" value="${selected}" />
  </div>`;
}

export function toggleField(id, on, onText, offText, hint = "") {
  const checked = on ? " checked" : "";
  return `<label class="toggle">
    <span class="toggle-copy"><span class="toggle-text">${escapeHtml(on ? onText : offText)}</span>${hint ? `<small>${escapeHtml(hint)}</small>` : ""}</span>
    <input type="checkbox" class="switch" id="${id}" data-on="${escapeHtml(onText)}" data-off="${escapeHtml(offText)}"${checked} />
  </label>`;
}
