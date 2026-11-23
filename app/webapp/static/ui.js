import { TIMES, t } from "./i18n.js";
import { haptic } from "./api.js";

export { escapeHtml } from "./html.js";

export function main() {
  return document.getElementById("main");
}

export function setHtml(html) {
  const root = main();
  root.innerHTML = html;
}

export function showError(err, retry) {
  const key =
    err && err.code === "not_owner"
      ? "denied"
      : err && (err.code === "tampered" || err.code === "expired" || err.code === "unauthorized" || err.status === 401)
        ? "auth"
        : "error";
  setHtml(`<div class="card err" role="alert"><p>${escapeHtml(t(key))}</p>
    <button type="button" class="primary" id="err-retry">${escapeHtml(t("retry"))}</button></div>`);
  const button = document.getElementById("err-retry");
  if (button) {
    button.addEventListener("click", () => {
      if (typeof retry === "function") retry();
      else location.reload();
    });
  }
}

let renderSeq = 0;

/** Start a navigation. A render is applied only while its ticket is still current. */
export function ticket() {
  renderSeq += 1;
  return renderSeq;
}

export function current(id) {
  return id === renderSeq;
}

export function setBusy(on) {
  const bar = document.getElementById("topbar");
  if (bar) bar.classList.toggle("on", Boolean(on));
}

/** Shimmer placeholders shaped like the screen that is loading. */
export function skeleton(kind = "home") {
  const line = (w, h = 14) => `<div class="sk" style="width:${w};height:${h}px"></div>`;
  const card = (inner, cls = "") => `<div class="card sk-card ${cls}">${inner}</div>`;
  const header = `<div class="header sk-header">${line("55%", 26)}${line("75%")}</div>`;
  if (kind === "list") {
    const row = `<div class="sk-row">${line("28px", 28)}${line("60%")}${line("15%")}</div>`;
    return `${header}${card(`${line("40%")}${row.repeat(6)}`)}`;
  }
  if (kind === "chat") {
    const section = card(`${line("35%", 18)}<div class="sk-gap"></div>${line("45%", 30)}${line("60%")}`);
    return `<div class="header sk-header">${line("45%", 26)}${line("25%")}</div>${section.repeat(3)}`;
  }
  const kpis = `<div class="kpis">${`<div class="kpi">${line("40%", 20)}${line("60%", 26)}${line("80%")}</div>`.repeat(3)}</div>`;
  return `${header}${kpis}${card(`${line("50%", 22)}${line("35%")}`, "sk-hero")}${card(`${line("40%")}<div class="sk" style="height:96px;margin-top:12px"></div>`)}${card(`${line("30%")}${line("50%", 26)}${line("70%")}`)}`;
}

/** Run an action with a spinner on the button and taps disabled until it settles. */
export async function withBusy(button, work) {
  if (!button || button.disabled) return undefined;
  const group = button.closest("[data-busy-group]");
  const peers = group ? [...group.querySelectorAll("button")] : [button];
  peers.forEach((node) => {
    node.disabled = true;
  });
  button.classList.add("busy");
  button.setAttribute("aria-busy", "true");
  try {
    return await work();
  } finally {
    button.classList.remove("busy");
    button.removeAttribute("aria-busy");
    peers.forEach((node) => {
      if (node.isConnected) node.disabled = false;
    });
  }
}

export function toast(text, kind = "ok") {
  let node = document.getElementById("toast");
  if (!node) {
    node = document.createElement("div");
    node.id = "toast";
    document.body.appendChild(node);
  }
  node.className = `toast ${kind} show`;
  node.textContent = text;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 2600);
}

export function bindPickers(root = document) {
  const showTime = (target, value) => {
    const show = document.getElementById(`${target}_show`);
    if (show && value) show.textContent = `${value} ⏰`;
  };
  root.querySelectorAll("[data-time-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      haptic("light");
      const target = btn.getAttribute("data-time-toggle");
      const edit = document.getElementById(`${target}_edit`);
      if (!edit) return;
      edit.hidden = !edit.hidden;
      btn.textContent = edit.hidden ? t("change") : t("hide");
    });
  });
  root.querySelectorAll(".chips").forEach((group) => {
    const target = group.getAttribute("data-chip-target");
    const hidden = document.getElementById(target);
    const custom = document.getElementById(`${target}_custom`);
    group.querySelectorAll("[data-value]").forEach((el) => {
      el.addEventListener("click", () => {
        haptic("light");
        const value = el.getAttribute("data-value");
        if (hidden) hidden.value = value;
        showTime(target, value);
        group.querySelectorAll("[data-value]").forEach((btn) => {
          btn.classList.toggle("selected", btn.getAttribute("data-value") === value);
        });
        if (custom && TIMES.includes(value)) custom.value = "";
      });
    });
    if (custom) {
      custom.addEventListener("change", () => {
        if (!custom.value) return;
        hidden.value = custom.value;
        showTime(target, custom.value);
        group.querySelectorAll("[data-value]").forEach((el) => {
          el.classList.toggle("selected", el.getAttribute("data-value") === custom.value);
        });
      });
    }
  });
  root.querySelectorAll(".toggle input[type=checkbox]").forEach((box) => {
    const label = box.closest(".toggle").querySelector(".toggle-text");
    const sync = () => {
      if (label) label.textContent = box.checked ? box.getAttribute("data-on") : box.getAttribute("data-off");
    };
    box.addEventListener("change", sync);
    sync();
  });
}

export function fieldValue(id) {
  const node = document.getElementById(id);
  return node ? node.value : null;
}

export function fieldChecked(id) {
  const node = document.getElementById(id);
  return node ? node.checked : null;
}

export {
  brandHeader,
  chatCard,
  formatNumber,
  kpiRow,
  metricGrid,
  normalizeTime,
  roleBadge,
  scheduleBlock,
  section,
  sparkChart,
  statsCards,
  toggleField,
  weekdayChips,
} from "./widgets.js";
export { t, currentLang } from "./i18n.js";
