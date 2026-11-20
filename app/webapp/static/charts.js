import { currentLang, dayLabel, t } from "./i18n.js";
import { escapeHtml, formatNumber } from "./ui.js";

/*
 * Dependency-free inline SVG charts: line/area, stacked bars, heatmap and horizontal bars.
 * Each chart is an HTML string (cheap to cache and repaint); bindCharts() wires the tap
 * tooltip afterwards. Every SVG has role="img" plus an aria-label summary.
 */

export const PALETTE = ["var(--accent)", "var(--header-1)", "#f59e0b", "#22c55e", "#f472b6", "#38bdf8"];
const W = 320;
const PAD = { l: 30, r: 8, t: 10, b: 20 };
const MONTHS = {
  uz: ["Yan", "Fev", "Mar", "Apr", "May", "Iyn", "Iyl", "Avg", "Sen", "Okt", "Noy", "Dek"],
  ru: ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
};
const registry = new Map();
let counter = 0;
let outsideBound = false;

function register(spec) {
  counter += 1;
  const id = `ch${counter}`;
  registry.set(id, spec);
  if (registry.size > 80) registry.delete(registry.keys().next().value);
  return id;
}

/* ---------- formatting ---------- */

const pad2 = (n) => String(n).padStart(2, "0");

function parseDay(iso) {
  const [y, m, d] = String(iso).split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1, 12);
}

export function shortDate(iso) {
  const date = parseDay(iso);
  return `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)}`;
}

export function dayTitle(iso) {
  const date = parseDay(iso);
  return `${dayLabel(((date.getDay() + 6) % 7) + 1)}, ${shortDate(iso)}`;
}

export function weekTitle(iso) {
  const end = parseDay(iso);
  end.setDate(end.getDate() + 6);
  return `${shortDate(iso)} – ${pad2(end.getDate())}.${pad2(end.getMonth() + 1)}`;
}

export function monthLabel(key, withYear = false) {
  const [y, m] = String(key).split("-").map(Number);
  const names = MONTHS[currentLang()] || MONTHS.en;
  const name = names[(m || 1) - 1] || key;
  return withYear ? `${name} ${y}` : name;
}

export function compact(value) {
  const n = Number(value) || 0;
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${+(n / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${+(n / 1e6).toFixed(1)}M`;
  if (abs >= 1e4) return `${+(n / 1e3).toFixed(0)}k`;
  if (abs >= 1e3) return `${+(n / 1e3).toFixed(1)}k`;
  return String(Math.round(n * 10) / 10);
}

function niceMax(value) {
  if (!(value > 0)) return 1;
  const exp = 10 ** Math.floor(Math.log10(value));
  const f = value / exp;
  const step = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
  return step * exp;
}

function axisPicks(count, most = 6) {
  if (count <= most) return [...Array(count).keys()];
  const out = [];
  const step = (count - 1) / (most - 1);
  for (let i = 0; i < most; i += 1) out.push(Math.round(i * step));
  return out;
}

function emptyBox(text, height) {
  return `<div class="chart-empty" style="min-height:${height}px"><span>📭</span>${escapeHtml(text || t("chEmpty"))}</div>`;
}

function legendHtml(series, totals = true) {
  return `<div class="legend">${series
    .map((s) => {
      const value = totals && s.total != null ? `: <strong>${escapeHtml(s.total)}</strong>` : "";
      return `<span class="legend-item"><i style="background:${s.color}"></i>${escapeHtml(s.name)}${value}</span>`;
    })
    .join("")}</div>`;
}

function wrap(id, svg, extra = "") {
  return `<div class="chart" data-chart="${id}">${svg}<div class="chart-tip" hidden></div></div>${extra}`;
}

function yAxis(max, height, fmt) {
  const inner = height - PAD.t - PAD.b;
  return [0, 0.5, 1]
    .map((f) => {
      const y = (PAD.t + inner * (1 - f)).toFixed(1);
      return `<line class="chart-grid" x1="${PAD.l}" x2="${W - PAD.r}" y1="${y}" y2="${y}"/>
        <text class="chart-axis" x="${PAD.l - 4}" y="${(+y + 3).toFixed(1)}" text-anchor="end">${escapeHtml(fmt(max * f))}</text>`;
    })
    .join("");
}

function xAxis(labels, xs, height, tick) {
  return axisPicks(labels.length)
    .map((i) => {
      const anchor = i === 0 && labels.length > 1 ? "start" : i === labels.length - 1 && labels.length > 1 ? "end" : "middle";
      return `<text class="chart-axis" x="${xs[i].toFixed(1)}" y="${height - 5}" text-anchor="${anchor}">${escapeHtml(tick(labels[i]))}</text>`;
    })
    .join("");
}

/* ---------- line / area ---------- */

/**
 * opts: { labels, series: [{name, color, values, area?, total?}], label, height?, max?,
 *         fmt?, tick?, title? (index -> tooltip heading), empty? }
 * Null values break the line (e.g. accuracy on a day without answers).
 */
export function lineChart(opts) {
  const { labels = [], series = [], label = "" } = opts;
  const height = opts.height || 150;
  const fmt = opts.fmt || compact;
  const tick = opts.tick || shortDate;
  const has = series.some((s) => s.values.some((v) => Number(v) > 0));
  if (!labels.length || !has) return emptyBox(opts.empty, height) + (opts.legend === false ? "" : legendHtml(series));
  let top = opts.max || 0;
  if (!opts.max) series.forEach((s) => s.values.forEach((v) => (top = Math.max(top, Number(v) || 0))));
  const max = opts.max || niceMax(top);
  const inner = W - PAD.l - PAD.r;
  const xs = labels.map((_, i) => PAD.l + (labels.length > 1 ? (inner * i) / (labels.length - 1) : inner / 2));
  const y = (v) => PAD.t + (height - PAD.t - PAD.b) * (1 - Math.min(Number(v) || 0, max) / max);
  const base = height - PAD.b;
  const shapes = series
    .map((s) => {
      const runs = [];
      let run = [];
      s.values.forEach((v, i) => {
        if (v == null) {
          if (run.length) runs.push(run);
          run = [];
        } else run.push([xs[i], y(v)]);
      });
      if (run.length) runs.push(run);
      return runs
        .map((pts) => {
          const line = pts.map(([px, py]) => `${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
          const area = s.area && pts.length > 1
            ? `<polygon class="chart-area" fill="${s.color}" points="${pts[0][0].toFixed(1)},${base} ${line} ${pts[pts.length - 1][0].toFixed(1)},${base}"/>`
            : "";
          const dots = pts.length === 1 || labels.length <= 14
            ? pts.map(([px, py]) => `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="2.4" fill="${s.color}"/>`).join("")
            : "";
          return `${area}<polyline class="chart-line" stroke="${s.color}" points="${line}"/>${dots}`;
        })
        .join("");
    })
    .join("");
  const title = opts.title || ((i) => dayTitle(labels[i]));
  const id = register({
    pick: (ratio) => nearest(xs, ratio * W),
    guideX: (i) => xs[i],
    html: (i) => tipHtml(title(i), series.map((s) => [s.color, s.name, s.values[i] == null ? "—" : fmt(s.values[i], true)])),
  });
  const aria = `${label}. ${series.map((s) => `${s.name}: ${s.total != null ? s.total : ""}`).join("; ")}`;
  const svg = `<svg viewBox="0 0 ${W} ${height}" role="img" aria-label="${escapeHtml(aria)}">
    <title>${escapeHtml(label)}</title>
    ${yAxis(max, height, fmt)}${xAxis(labels, xs, height, tick)}${shapes}
    <line class="chart-guide" x1="0" x2="0" y1="${PAD.t}" y2="${base}" visibility="hidden"/>
  </svg>`;
  return wrap(id, svg, opts.legend === false ? "" : legendHtml(series));
}

/* ---------- stacked bars ---------- */

/** opts: { labels, series: [{name, color, values, total?}], label, height?, fmt?, tick?, title?, empty?, more? (i -> extra tooltip rows) } */
export function barChart(opts) {
  const { labels = [], series = [], label = "" } = opts;
  const height = opts.height || 150;
  const fmt = opts.fmt || compact;
  const tick = opts.tick || shortDate;
  const sums = labels.map((_, i) => series.reduce((acc, s) => acc + (Number(s.values[i]) || 0), 0));
  const top = Math.max(0, ...sums);
  if (!labels.length || top <= 0) return emptyBox(opts.empty, height) + (opts.legend === false ? "" : legendHtml(series));
  const max = niceMax(top);
  const inner = W - PAD.l - PAD.r;
  const slot = inner / labels.length;
  const bw = Math.max(2, Math.min(28, slot * 0.68));
  const xs = labels.map((_, i) => PAD.l + slot * (i + 0.5));
  const scale = (height - PAD.t - PAD.b) / max;
  const base = height - PAD.b;
  const bars = labels
    .map((_, i) => {
      let yTop = base;
      return series
        .map((s) => {
          const h = (Number(s.values[i]) || 0) * scale;
          if (h <= 0) return "";
          yTop -= h;
          return `<rect class="chart-bar" x="${(xs[i] - bw / 2).toFixed(1)}" y="${yTop.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(h, 1).toFixed(1)}" rx="${Math.min(3, bw / 3).toFixed(1)}" fill="${s.color}"/>`;
        })
        .join("");
    })
    .join("");
  const title = opts.title || ((i) => dayTitle(labels[i]));
  const id = register({
    pick: (ratio) => nearest(xs, ratio * W),
    guideX: (i) => xs[i],
    html: (i) => {
      const rows = series.map((s) => [s.color, s.name, fmt(s.values[i] || 0, true)]);
      if (series.length > 1 && opts.total !== false) rows.push(["transparent", t("chTotal"), fmt(sums[i], true)]);
      if (opts.more) rows.push(...opts.more(i));
      return tipHtml(title(i), rows);
    },
  });
  const aria = `${label}. ${series.map((s) => `${s.name}: ${s.total != null ? s.total : ""}`).join("; ")}`;
  const svg = `<svg viewBox="0 0 ${W} ${height}" role="img" aria-label="${escapeHtml(aria)}">
    <title>${escapeHtml(label)}</title>
    ${yAxis(max, height, fmt)}${xAxis(labels, xs, height, tick)}${bars}
    <line class="chart-guide" x1="0" x2="0" y1="${PAD.t}" y2="${base}" visibility="hidden"/>
  </svg>`;
  return wrap(id, svg, opts.legend === false ? "" : legendHtml(series));
}

/* ---------- heatmap (weekday x hour) ---------- */

/** cells[dow 0=Mon..6][hour 0..23] */
export function heatmap(cells, opts = {}) {
  const grid = Array.isArray(cells) && cells.length === 7 ? cells : [];
  const max = Math.max(0, ...grid.flat().map((v) => Number(v) || 0));
  if (!grid.length || max <= 0) return emptyBox(opts.empty, 120);
  const left = 26;
  const cw = (W - left - 4) / 24;
  const ch = 13;
  const gap = 2;
  const height = 7 * (ch + gap) + 16;
  const unit = opts.unit || t("chAnswersUnit");
  const rects = grid
    .map((row, d) =>
      row
        .map((v, h) => {
          const value = Number(v) || 0;
          const alpha = value ? 0.18 + 0.82 * (value / max) : 0.06;
          return `<rect class="heat-cell" data-i="${d * 24 + h}" x="${(left + h * cw).toFixed(1)}" y="${d * (ch + gap)}" width="${(cw - gap).toFixed(1)}" height="${ch}" rx="2" fill="var(--accent)" fill-opacity="${alpha.toFixed(2)}"/>`;
        })
        .join(""),
    )
    .join("");
  const days = [1, 2, 3, 4, 5, 6, 7]
    .map((d) => `<text class="chart-axis" x="${left - 4}" y="${(d - 1) * (ch + gap) + ch - 3}" text-anchor="end">${escapeHtml(dayLabel(d))}</text>`)
    .join("");
  const hours = [0, 6, 12, 18, 23]
    .map((h) => `<text class="chart-axis" x="${(left + h * cw + (cw - gap) / 2).toFixed(1)}" y="${height - 3}" text-anchor="middle">${pad2(h)}</text>`)
    .join("");
  let best = [0, 0];
  grid.forEach((row, d) => row.forEach((v, h) => (Number(v) > grid[best[0]][best[1]] ? (best = [d, h]) : null)));
  const peak = `${dayLabel(best[0] + 1)} ${pad2(best[1])}:00`;
  const id = register({
    cell: true,
    html: (i) => {
      const d = Math.floor(i / 24);
      const h = i % 24;
      return tipHtml(`${dayLabel(d + 1)} ${pad2(h)}:00–${pad2((h + 1) % 24)}:00`, [["var(--accent)", unit, formatNumber(grid[d][h])]]);
    },
  });
  const label = opts.label || "";
  const svg = `<svg viewBox="0 0 ${W} ${height}" role="img" aria-label="${escapeHtml(`${label}. ${t("chPeak")}: ${peak}`)}">
    <title>${escapeHtml(label)}</title>${days}${hours}${rects}</svg>`;
  return wrap(id, svg, `<p class="muted chart-note">🔥 ${escapeHtml(t("chPeak"))}: <b>${escapeHtml(peak)}</b></p>`);
}

/* ---------- horizontal comparison bars ---------- */

/** rows: [{label, values: [..]}], series: [{name, color}] — values printed, no tooltip needed. */
export function hbars(rows, series, opts = {}) {
  if (!rows.length) return emptyBox(opts.empty, 80);
  const tops = series.map((_, k) => Math.max(1, ...rows.map((r) => Number(r.values[k]) || 0)));
  const body = rows
    .map(
      (r) => `<div class="hbar-row">
      <div class="hbar-name">${escapeHtml(r.label)}</div>
      ${series
        .map(
          (s, k) => `<div class="hbar-line"><div class="hbar-track"><i style="width:${((100 * (Number(r.values[k]) || 0)) / tops[k]).toFixed(1)}%;background:${s.color}"></i></div><b>${escapeHtml(formatNumber(r.values[k] || 0))}</b></div>`,
        )
        .join("")}
    </div>`,
    )
    .join("");
  return `<div class="hbars" role="list" aria-label="${escapeHtml(opts.label || "")}">${body}</div>${legendHtml(series, false)}`;
}

/* ---------- tooltip wiring ---------- */

function nearest(xs, x) {
  let best = 0;
  xs.forEach((value, i) => {
    if (Math.abs(value - x) < Math.abs(xs[best] - x)) best = i;
  });
  return best;
}

function tipHtml(title, rows) {
  return `<div class="tip-title">${escapeHtml(title)}</div>${rows
    .map(([color, name, value]) => `<div class="tip-row"><i style="background:${color}"></i><span>${escapeHtml(name)}</span><b>${escapeHtml(value)}</b></div>`)
    .join("")}`;
}

function hideAll(except) {
  document.querySelectorAll(".chart.tipping").forEach((node) => {
    if (node === except) return;
    node.classList.remove("tipping");
    const tip = node.querySelector(".chart-tip");
    if (tip) tip.hidden = true;
    const guide = node.querySelector(".chart-guide");
    if (guide) guide.setAttribute("visibility", "hidden");
    node.querySelectorAll(".heat-cell.on").forEach((c) => c.classList.remove("on"));
  });
}

function show(node, spec, event) {
  const svg = node.querySelector("svg");
  const tip = node.querySelector(".chart-tip");
  if (!svg || !tip) return;
  const box = svg.getBoundingClientRect();
  if (!box.width) return;
  let index;
  if (spec.cell) {
    const hit = document.elementFromPoint(event.clientX, event.clientY);
    if (!hit || !hit.matches || !hit.matches(".heat-cell")) return;
    index = Number(hit.getAttribute("data-i"));
    node.querySelectorAll(".heat-cell.on").forEach((c) => c.classList.remove("on"));
    hit.classList.add("on");
  } else {
    index = spec.pick((event.clientX - box.left) / box.width);
    const guide = node.querySelector(".chart-guide");
    if (guide) {
      const gx = spec.guideX(index).toFixed(1);
      guide.setAttribute("x1", gx);
      guide.setAttribute("x2", gx);
      guide.setAttribute("visibility", "visible");
    }
  }
  hideAll(node);
  tip.innerHTML = spec.html(index);
  tip.hidden = false;
  node.classList.add("tipping");
  const host = node.getBoundingClientRect();
  const x = event.clientX - host.left;
  const width = tip.offsetWidth || 140;
  tip.style.left = `${Math.max(0, Math.min(host.width - width, x - width / 2))}px`;
  tip.style.top = `${Math.max(0, event.clientY - host.top - tip.offsetHeight - 14)}px`;
}

/** Wire tap/hover tooltips on every chart under root (idempotent). */
export function bindCharts(root = document) {
  root.querySelectorAll(".chart[data-chart]").forEach((node) => {
    if (node.dataset.bound) return;
    const spec = registry.get(node.getAttribute("data-chart"));
    if (!spec) return;
    node.dataset.bound = "1";
    const handler = (event) => show(node, spec, event);
    node.addEventListener("pointerdown", handler);
    node.addEventListener("pointermove", (event) => {
      if (event.pointerType === "mouse" || event.buttons) handler(event);
    });
    node.addEventListener("pointerleave", (event) => {
      if (event.pointerType === "mouse") hideAll(null);
    });
  });
  if (!outsideBound) {
    outsideBound = true;
    document.addEventListener("pointerdown", (event) => {
      if (!event.target.closest || !event.target.closest(".chart")) hideAll(null);
    });
  }
}

/* ---------- small shared pieces ---------- */

/** Period switcher 7/30/90; buttons carry data-days. */
export function periodChips(days, periods = [7, 30, 90]) {
  return `<div class="seg" role="tablist" aria-label="${escapeHtml(t("chPeriod"))}">${periods
    .map((d) => `<button type="button" role="tab" aria-selected="${d === days}" class="seg-btn${d === days ? " on" : ""}" data-days="${d}">${escapeHtml(t("chDays", { n: d }))}</button>`)
    .join("")}</div>`;
}

/** KPI with the change vs the previous period. kind "pp" shows percentage points. */
export function deltaKpi(icon, value, label, change, kind = "pct") {
  let badge = `<span class="delta flat">${escapeHtml(t("chNoPrev"))}</span>`;
  if (change != null) {
    const n = Number(change);
    const cls = n > 0 ? "up" : n < 0 ? "down" : "flat";
    const arrow = n > 0 ? "▲" : n < 0 ? "▼" : "•";
    const text = kind === "pp" ? `${n > 0 ? "+" : ""}${n} ${t("chPp")}` : `${n > 0 ? "+" : ""}${n}%`;
    badge = `<span class="delta ${cls}">${arrow} ${escapeHtml(text)}</span>`;
  }
  return `<div class="kpi"><div class="kpi-icon">${icon}</div>
    <div class="kpi-value">${escapeHtml(value)}</div>
    <div class="kpi-label">${escapeHtml(label)}</div>${badge}</div>`;
}

export function chartCard(title, body, extra = "") {
  return `<div class="card chart-card"><div class="card-title">${escapeHtml(title)}${extra}</div>${body}</div>`;
}
