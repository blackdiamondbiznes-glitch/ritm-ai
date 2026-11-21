import { firstChatId, go, haptic, isManager, memberData, roles, state } from "./api.js";
import { brandHeader, chatCard, escapeHtml, formatNumber, kpiRow, setHtml, sparkChart, t } from "./ui.js";

/** Owners see their plan; so do people with no role yet (they may become owners). */
export function showsPlan() {
  const list = roles();
  return !list || list.includes("owner") || list.length === 0;
}

export function renderHome() {
  if (!isManager()) {
    renderMemberHome();
    return;
  }
  const dash = state.dash || { plan: {}, stats: {}, chats: [] };
  const plan = dash.plan || {};
  const chats = dash.chats || [];
  const member = memberData();
  setHtml(`
    ${brandHeader()}
    ${kpiRow(dash.stats)}
    <button type="button" class="action hero" data-action="post">
      <div class="hero-icon">🤖</div>
      <div><div class="hero-title">${escapeHtml(t("actionPost"))}</div>
      <div class="hero-sub">${escapeHtml(t("actionPostSub"))}</div></div>
      <div class="hero-arrow">›</div>
    </button>
    <div class="grid three">
      ${action("quiz", "📝", t("actionQuiz"))}
      ${action("board", "🏆", t("actionBoard"))}
      ${action("settings", "⚙️", t("actionSettings"))}
    </div>
    ${sparkChart(dash.stats && dash.stats.daily)}
    ${member ? myResultsCard(member, true) : ""}
    ${showsPlan() ? planCard(plan) : ""}
    ${chats.length ? chats.map((chat) => chatCard(withPlan(chat, plan), `data-go="${chat.id}"`)).join("") : `<div class="card muted">${escapeHtml(t("empty"))}</div>`}
  `);
  bindMine();
  document.querySelectorAll("[data-action]").forEach((node) => {
    node.addEventListener("click", () => onAction(node.getAttribute("data-action"), chats));
  });
  document.querySelectorAll("[data-go]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(`chats/${node.getAttribute("data-go")}`);
    });
  });
}

/** The plan badge belongs to the caller; never show it on chats owned by someone else. */
export function withPlan(chat, plan) {
  return chat.role === "owner" || !chat.role ? { ...chat, plan_name: plan && plan.plan_name } : chat;
}

function renderMemberHome() {
  const dash = state.dash || {};
  const member = memberData();
  if (!member) {
    setHtml(`
      ${brandHeader()}
      <div class="card">
        <div class="card-title">👋 ${escapeHtml(t("welcomeTitle"))}</div>
        <p>${escapeHtml(t("welcomeMember"))}</p>
      </div>
      ${ownCta()}
      ${state.dash && showsPlan() ? planCard(dash.plan || {}) : ""}
    `);
    bindMine();
    return;
  }
  const totals = member.totals || {};
  setHtml(`
    ${brandHeader()}
    <div class="kpis">
      ${kpi("🏆", formatNumber(totals.week_points || 0), t("kpiWeekPoints"))}
      ${kpi("⭐", formatNumber(totals.points_total || 0), t("kpiTotalPoints"))}
      ${kpi("🎯", totals.accuracy != null ? `${totals.accuracy}%` : "—", t("kpiAccuracy"))}
    </div>
    <div class="kpi-hint">${escapeHtml(t("answersCount", { n: totals.answers || 0, c: totals.correct || 0 }))}</div>
    ${myResultsCard(member, false)}
    <button type="button" class="ghost wide" data-mine="history">📜 ${escapeHtml(t("historyOpen"))}</button>
    ${ownCta()}
  `);
  bindMine();
}

/** Regular users may own a group or channel too: one tap to the connect screen. */
function ownCta() {
  return `<div class="card own-cta">
    <div class="card-title">➕ ${escapeHtml(t("ownCtaTitle"))}</div>
    <p class="muted small-text">${escapeHtml(t("ownCtaSub"))}</p>
    <button type="button" class="primary" data-mine="profile/connect">${escapeHtml(t("ownCtaBtn"))}</button>
  </div>`;
}

function kpi(icon, value, label) {
  return `<div class="kpi"><div class="kpi-icon">${icon}</div>
    <div class="kpi-value">${escapeHtml(value)}</div>
    <div class="kpi-label">${escapeHtml(label)}</div></div>`;
}

/** Per-chat points, weekly rank and accuracy. `compact` is the card for people with several roles. */
export function myResultsCard(member, compact) {
  const chats = member.chats || [];
  const rows = chats
    .map((chat) => {
      const rank =
        chat.week_rank != null
          ? t("rankOf", { r: chat.week_rank, n: chat.week_members })
          : t("noRankYet");
      const facts = [
        `🏆 ${rank}`,
        `${formatNumber(chat.week_points || 0)} ${t("points")} · ${t("thisWeek")}`,
        `⭐ ${formatNumber(chat.points_total || 0)} ${t("points")}`,
        `🎯 ${chat.accuracy != null ? `${chat.accuracy}%` : "—"}`,
      ];
      return `<button type="button" class="my-chat" data-mine="board/${chat.id}">
        <div class="chat-name">${escapeHtml(chat.title || "Chat")}</div>
        <div class="my-stats">${facts.map((f) => `<span class="fact">${escapeHtml(f)}</span>`).join("")}</div>
      </button>`;
    })
    .join("");
  const more = compact
    ? `<button type="button" class="ghost small" data-mine="history">📜 ${escapeHtml(t("historyOpen"))}</button>`
    : "";
  return `<div class="card my-card">
    <div class="row space"><div class="card-title">🙋 ${escapeHtml(t("myResults"))}</div>${more}</div>
    ${rows}
  </div>`;
}

function bindMine() {
  document.querySelectorAll("[data-mine]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(node.getAttribute("data-mine"));
    });
  });
}

function action(name, icon, label) {
  return `<button type="button" class="action" data-action="${name}">
    <div class="icon">${icon}</div>${escapeHtml(label)}
  </button>`;
}

function onAction(name, chats) {
  haptic("light");
  const only = firstChatId();
  const first = only || (chats[0] && chats[0].id);
  if (name === "board") {
    go(first ? `board/${first}` : "board");
    return;
  }
  if (name === "post" || name === "quiz" || name === "settings") {
    go(first ? `chats/${first}` : "chats");
  }
}

export function planCard(plan) {
  const name = escapeHtml(plan.plan_name || "—");
  const kindKey = plan.kind === "trial" ? "trial" : plan.kind === "active" ? "active" : "free";
  const kind = t(kindKey);
  const days =
    plan.days_left != null && plan.kind !== "free" ? `<p>${escapeHtml(t("daysLeft", { n: plan.days_left }))}</p>` : "";
  const used = Number(plan.ai_used || 0);
  const limit = Number(plan.ai_limit || 0);
  const left = plan.ai_left != null ? Number(plan.ai_left) : Math.max(0, limit - used);
  const pct = limit > 0 ? Math.max(0, Math.min(100, Math.round((left / limit) * 100))) : 0;
  const bar = `<div class="ai-left">${escapeHtml(t("aiLeft", { n: formatNumber(left) }))}</div>
    <div class="progress" aria-hidden="true"><span style="width:${pct}%"></span></div>
    <div class="muted small-text">${escapeHtml(t("aiOf", { n: formatNumber(limit) }))}</div>`;
  let founder = "";
  if (plan.founder_keep) {
    founder = `<p class="muted">${escapeHtml(t("founderKeep"))}</p>`;
  } else if (plan.founder && plan.founder_remaining > 0) {
    founder = `<p class="muted">${escapeHtml(t("founderSale", { slots: plan.founder_slots, left: plan.founder_remaining }))}</p>`;
  }
  const pending = plan.pending
    ? `<p class="muted">${escapeHtml(t("pending"))}: ${plan.pending.ref ? `<b>${escapeHtml(plan.pending.ref)}</b> · ` : ""}${escapeHtml(formatNumber(plan.pending.amount_uzs))} so'm</p>`
    : "";
  return `<div class="card">
    <div class="card-title">${escapeHtml(t("plan"))}</div>
    <div class="big">${name}</div>
    <p>${escapeHtml(kind)}</p>
    ${days}
    ${bar}
    ${founder}
    ${pending}
  </div>`;
}
