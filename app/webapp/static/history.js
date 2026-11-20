import { cached, go, haptic, load } from "./api.js";
import { barChart, bindCharts, chartCard, lineChart, PALETTE, weekTitle } from "./charts.js";
import { brandHeader, current, escapeHtml, setBusy, setHtml, showError, skeleton, t } from "./ui.js";
import { myResultsCard } from "./home.js";

const PATH = "/api/me/stats";
export const MY_CHARTS = "/api/me/charts?weeks=12";

/** The member's own quiz answers: what they picked, the right answer, and when. */
export async function renderHistory(seq) {
  const hit = cached(PATH);
  if (hit) paint(hit);
  else setHtml(skeleton("list"));
  setBusy(true);
  try {
    const data = await load(PATH, { maxAge: hit ? 0 : 15000 });
    if (current(seq)) paint(data);
    fillCharts(seq);
  } catch (err) {
    if (current(seq) && !hit) showError(err);
  } finally {
    if (current(seq)) setBusy(false);
  }
}

function paint(data) {
  const member = data && data.member;
  if (!member) {
    setHtml(`
      ${brandHeader()}
      <h2 class="page-title">📜 ${escapeHtml(t("historyTitle"))}</h2>
      <div class="card muted">${escapeHtml(t("historyEmpty"))}</div>
    `);
    return;
  }
  const totals = member.totals || {};
  const rows = (member.history || []).map(historyRow).join("");
  setHtml(`
    ${brandHeader()}
    <h2 class="page-title">📜 ${escapeHtml(t("historyTitle"))}</h2>
    <p class="muted page-sub">${escapeHtml(
      t("answersCount", { n: totals.answers || 0, c: totals.correct || 0 }),
    )}${totals.accuracy != null ? ` · 🎯 ${totals.accuracy}%` : ""}</p>
    ${myResultsCard(member, false)}
    <div id="myCharts">${chartsHtml(cached(MY_CHARTS))}</div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("historyLast"))}</div>
      ${rows || `<p class="muted">${escapeHtml(t("historyEmpty"))}</p>`}
    </div>
  `);
  bindCharts();
  document.querySelectorAll("[data-mine]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(node.getAttribute("data-mine"));
    });
  });
}

function historyRow(row) {
  const mark = row.is_correct ? "✅" : "❌";
  const chosen = row.chosen != null ? row.chosen : "—";
  const answer = row.is_correct
    ? `<div class="hist-a ok-text">${escapeHtml(t("yourAnswer"))}: ${escapeHtml(chosen)}</div>`
    : `<div class="hist-a">${escapeHtml(t("yourAnswer"))}: ${escapeHtml(chosen)}</div>
       <div class="hist-a muted">${escapeHtml(t("rightAnswer"))}: ${escapeHtml(row.correct || "—")}</div>`;
  return `<div class="hist-row">
    <div class="hist-mark">${mark}</div>
    <div class="hist-body">
      <div class="hist-q">${escapeHtml(row.question || "")}</div>
      ${answer}
      <div class="hist-meta">${escapeHtml(row.chat_title || "")}${row.answered_at ? ` · ${escapeHtml(when(row.answered_at))}` : ""}</div>
    </div>
  </div>`;
}

function when(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(date.getDate())}.${pad(date.getMonth() + 1)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Own points per week and accuracy trend (cached copy first, then fresh). */
async function fillCharts(seq) {
  try {
    const data = await load(MY_CHARTS, { maxAge: 30000 });
    const box = document.getElementById("myCharts");
    if (!current(seq) || !box) return;
    box.innerHTML = chartsHtml(data);
    bindCharts(box);
  } catch {
    /* charts are optional on this page */
  }
}

function chartsHtml(data) {
  if (!data || !Array.isArray(data.series)) return "";
  const totals = data.totals || {};
  if (!totals.answers) return "";
  const labels = data.series.map((row) => row.week);
  const title = (i) => weekTitle(labels[i]);
  return `${chartCard(
    `⭐ ${t("chMyPoints")}`,
    barChart({
      label: t("chMyPoints"),
      labels,
      title,
      series: [{ name: t("chPoints"), color: PALETTE[0], values: data.series.map((r) => r.points), total: totals.points }],
    }),
  )}${chartCard(
    `🎯 ${t("chMyAccuracy")}`,
    lineChart({
      label: t("chMyAccuracy"),
      labels,
      title,
      max: 100,
      fmt: (v) => `${Math.round(Number(v) || 0)}%`,
      series: [
        {
          name: t("chAccuracy"),
          color: PALETTE[3],
          values: data.series.map((r) => r.accuracy),
          area: true,
          total: totals.accuracy != null ? `${totals.accuracy}%` : "—",
        },
      ],
    }),
  )}`;
}
