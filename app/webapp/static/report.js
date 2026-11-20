import { cached, go, haptic, load, prefetch, state } from "./api.js";
import { barChart, bindCharts, chartCard, deltaKpi, heatmap, hbars, lineChart, PALETTE, periodChips, shortDate, weekTitle } from "./charts.js";
import { brandHeader, current, escapeHtml, formatNumber, setBusy, setHtml, showError, skeleton, t } from "./ui.js";

/* Hisobot: the owner/admin charts home. Every number comes from /api/charts (real answers, posts, quizzes). */

const DAYS_KEY = "ritm.chartDays";
const PERIODS = [7, 30, 90];

export function chartDays() {
  let saved = 7;
  try {
    saved = Number(localStorage.getItem(DAYS_KEY));
  } catch {
    /* storage blocked: keep the default */
  }
  return PERIODS.includes(saved) ? saved : 7;
}

export function chartPath(scope, days = chartDays()) {
  return `/api/charts?chat=${scope}&days=${days}`;
}

export async function renderReport(chatId, seq) {
  const scope = chatId ? String(chatId) : "all";
  const days = chartDays();
  const path = chartPath(scope, days);
  const hit = cached(path);
  if (hit) paint(hit, scope);
  else setHtml(skeleton("list"));
  setBusy(true);
  try {
    const data = await load(path, { maxAge: hit ? 0 : 30000 });
    if (current(seq)) {
      paint(data, scope);
      // Make the other periods of this scope instant to switch to.
      prefetch(PERIODS.filter((d) => d !== days).map((d) => chartPath(scope, d)));
    }
  } catch (err) {
    if (current(seq) && !hit) showError(err);
  } finally {
    if (current(seq)) setBusy(false);
  }
}

function scopeChats(data) {
  const all = cached(chartPath("all"));
  const list = (all && all.chats) || (data.scope === "all" ? data.chats : null) || (state.dash && state.dash.chats) || data.chats || [];
  return list.map((chat) => ({ id: String(chat.id), title: chat.title || `#${chat.id}` }));
}

function paint(data, scope) {
  const chats = scopeChats(data);
  const series = data.series || [];
  const labels = series.map((row) => row.date);
  const totals = (data.totals && data.totals.current) || {};
  const change = (data.totals && data.totals.change) || {};
  const pick = (key) => series.map((row) => row[key]);
  const sum = (key) => formatNumber(totals[key] || 0);
  const chips = [["all", `🌐 ${t("chAll")}`], ...chats.map((c) => [c.id, c.title])]
    .map(([id, title]) => `<button type="button" class="chip-btn${id === scope ? " selected" : ""}" data-scope="${escapeHtml(id)}">${escapeHtml(title)}</button>`)
    .join("");
  const weeks = data.weekly || [];
  const weekly = barChart({
    label: `${t("chParticipants")} · ${t("chWeekly")}`,
    labels: weeks.map((w) => w.week),
    tick: shortDate,
    title: (i) => weekTitle(weeks[i].week),
    height: 120,
    series: [{ name: t("chParticipants"), color: PALETTE[1], values: weeks.map((w) => w.participants) }],
    more: (i) => [
      [PALETTE[0], t("chAnswers"), formatNumber(weeks[i].answers)],
      [PALETTE[3], t("chAccuracy"), weeks[i].accuracy != null ? `${weeks[i].accuracy}%` : "—"],
    ],
    legend: false,
  });
  const compare = (data.compare || []).map((c) => ({ label: c.title || `#${c.id}`, values: [c.answers, c.participants] }));
  const top = data.top || [];
  const topSeries = top.map((p, i) => ({ name: p.name, color: PALETTE[i % PALETTE.length], values: p.series, total: formatNumber(p.points) }));
  const accuracyFmt = (v) => `${Math.round(Number(v) || 0)}%`;
  const chatTitle = scope !== "all" ? (chats.find((c) => c.id === scope) || {}).title || "" : t("chAll");
  setHtml(`
    ${brandHeader()}
    <h2 class="page-title">📊 ${escapeHtml(t("navReport"))}</h2>
    <p class="muted page-sub">${escapeHtml(chatTitle)} · ${escapeHtml(shortDate(data.start))}–${escapeHtml(shortDate(data.end))} · ${escapeHtml((data.zones || [data.timezone]).join(", "))}</p>
    <div class="chips chips-scroll">${chips}</div>
    ${periodChips(data.days)}
    <div class="kpis">
      ${deltaKpi("💬", sum("answers"), t("chAnswers"), change.answers)}
      ${deltaKpi("👥", sum("participants"), t("chParticipants"), change.participants)}
      ${deltaKpi("🧩", sum("quizzes"), t("chQuizzes"), change.quizzes)}
      ${deltaKpi("📝", sum("posts"), t("chPosts"), change.posts)}
      ${deltaKpi("🎯", totals.accuracy != null ? `${totals.accuracy}%` : "—", t("chAccuracy"), change.accuracy, "pp")}
    </div>
    <p class="muted chart-note">${escapeHtml(t("chVsPrev", { n: data.days }))}</p>
    ${chartCard(
      `📈 ${t("chActivity")}`,
      lineChart({
        label: t("chActivity"),
        labels,
        series: [
          { name: t("chAnswers"), color: PALETTE[0], values: pick("answers"), area: true, total: sum("answers") },
          { name: t("chQuizzes"), color: PALETTE[1], values: pick("quizzes"), total: sum("quizzes") },
          { name: t("chPosts"), color: PALETTE[2], values: pick("posts"), total: sum("posts") },
        ],
      }),
    )}
    ${chartCard(
      `👥 ${t("chParticipantsDay")}`,
      barChart({
        label: t("chParticipantsDay"),
        labels,
        series: [{ name: t("chParticipants"), color: PALETTE[3], values: pick("participants") }],
        legend: false,
      }) + `<div class="card-sub">${escapeHtml(t("chParticipants"))} · ${escapeHtml(t("chWeekly"))}</div>${weekly}`,
    )}
    ${chartCard(
      `🎯 ${t("chAccuracy")}`,
      lineChart({
        label: t("chAccuracy"),
        labels,
        max: 100,
        fmt: accuracyFmt,
        series: [{ name: t("chAccuracy"), color: PALETTE[3], values: pick("accuracy"), area: true, total: totals.accuracy != null ? `${totals.accuracy}%` : "—" }],
      }),
    )}
    ${chartCard(`🕒 ${t("chHeatmap")}`, heatmap(data.heatmap && data.heatmap.cells, { label: t("chHeatmap") }))}
    ${compare.length ? chartCard(`⚖️ ${t("chCompare")}`, hbars(compare, [
      { name: t("chAnswers"), color: PALETTE[0] },
      { name: t("chParticipants"), color: PALETTE[3] },
    ], { label: t("chCompare") })) : ""}
    ${chartCard(
      `🏆 ${t("chTop")}`,
      (top.length
        ? lineChart({ label: t("chTop"), labels, series: topSeries, fmt: (v) => formatNumber(v) })
        : `<div class="chart-empty"><span>📭</span>${escapeHtml(t("chEmpty"))}</div>`) +
        (scope !== "all" ? `<button type="button" class="ghost wide" id="openBoard">🏆 ${escapeHtml(t("boardTitle"))}</button>` : ""),
    )}
  `);
  bindCharts();
  document.querySelectorAll("[data-scope]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      const id = node.getAttribute("data-scope");
      go(id === "all" ? "report" : `report/${id}`);
    });
  });
  document.querySelectorAll("[data-days]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      try {
        localStorage.setItem(DAYS_KEY, node.getAttribute("data-days"));
      } catch {
        /* storage blocked: the period resets next time */
      }
      go(scope === "all" ? "report" : `report/${scope}`);
    });
  });
  const open = document.getElementById("openBoard");
  if (open) {
    open.onclick = () => {
      haptic("light");
      go(`board/${scope}`);
    };
  }
}
