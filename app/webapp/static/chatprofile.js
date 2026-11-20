import { api, cached, forget, go, haptic, load, remember, tg } from "./api.js";
import { current, escapeHtml, setBusy, setHtml, showError, skeleton, t, toast, withBusy } from "./ui.js";

/** The bot wizard's profile questions as one form. Validation and storage stay on the server. */
export function profilePath(id) {
  return `/api/chats/${id}/profile`;
}

export async function renderChatProfile(id, seq) {
  const path = profilePath(id);
  const hit = cached(path);
  if (hit) paint(id, hit, seq);
  else setHtml(skeleton("chat"));
  setBusy(true);
  try {
    const data = await load(path, { maxAge: 0 });
    if (current(seq) && data !== hit) paint(id, data, seq);
  } catch (err) {
    if (current(seq) && !hit) showError(err);
  } finally {
    if (current(seq)) setBusy(false);
  }
}

/** Human labels for a stored profile, when the options are cached. */
export function profileLabels(id, profile) {
  const form = cached(profilePath(id));
  if (!form || !profile) return null;
  const opts = form.options || {};
  const label = (list, code) => ((list || []).find((item) => item.code === code) || {}).label || code;
  return {
    niche: label(opts.niches, profile.niche_code),
    tone: label(opts.tones, profile.tone),
    audience: label(opts.audiences, profile.audience_level),
    language: label(opts.languages, profile.language),
  };
}

function chips(name, list, selected, extra = "") {
  const buttons = list
    .map(
      (item) =>
        `<button type="button" class="chip-btn${item.code === selected ? " selected" : ""}" data-field="${name}" data-value="${escapeHtml(item.code)}">${escapeHtml(item.label)}</button>`,
    )
    .join("");
  return `<div class="chips wrap" data-group="${name}">${buttons}${extra}</div>`;
}

function field(label, inner, name, hint = "") {
  return `<div class="form-field">
    <div class="form-label">${escapeHtml(label)}</div>
    ${inner}
    ${hint ? `<div class="form-hint">${escapeHtml(hint)}</div>` : ""}
    <div class="form-err" id="err_${name}" hidden></div>
  </div>`;
}

function paint(id, data, seq) {
  const opts = data.options || {};
  const prof = data.profile || {};
  const presetCodes = (opts.niches || []).map((item) => item.code);
  const niche = prof.niche_code || "";
  const custom = niche && !presetCodes.includes(niche);
  const zone = prof.timezone || data.default_timezone || "Asia/Tashkent";
  const readOnly = !data.can_edit;
  const back = tg && tg.BackButton ? "" : `<button type="button" class="back-link" id="cpBack" aria-label="‹">‹</button>`;
  const zones = (opts.timezones || [])
    .map((tz) => `<option value="${escapeHtml(tz)}"${tz === zone ? " selected" : ""}>${escapeHtml(tz)}</option>`)
    .join("");
  const desc = prof.niche_description || "";
  setHtml(`
    <div class="sub-head">${back}<h2 class="page-title">${escapeHtml(data.profile ? t("cpEdit") : t("cpFill"))}</h2></div>
    <p class="muted pad-x">${escapeHtml((data.chat && data.chat.title) || "")}</p>
    ${readOnly ? `<div class="readonly-note">🔒 ${escapeHtml(t("readOnly"))}</div>` : ""}
    <form class="card cp-form${readOnly ? " readonly" : ""}" id="cpForm" novalidate>
      ${field(
        t("cpNiche"),
        chips("niche", opts.niches || [], custom ? "" : niche, `<button type="button" class="chip-btn${custom ? " selected" : ""}" data-field="niche" data-value="">${escapeHtml(opts.other || "…")}</button>`) +
          `<input type="text" class="input" id="niche_custom" maxlength="${opts.niche_max || 200}" placeholder="${escapeHtml(t("cpNicheCustom"))}" value="${escapeHtml(custom ? niche : "")}"${custom ? "" : " hidden"} />`,
        "niche_code",
      )}
      ${field(
        t("cpDesc"),
        `<textarea class="input" id="niche_description" rows="3" maxlength="${opts.desc_max || 500}" placeholder="${escapeHtml(t("cpDescHint"))}">${escapeHtml(desc)}</textarea>
         <div class="counter"><span id="descCount">${desc.length}</span>/${opts.desc_max || 500}</div>`,
        "niche_description",
      )}
      ${field(t("cpTone"), chips("tone", opts.tones || [], prof.tone || ""), "tone")}
      ${field(t("cpAudience"), chips("audience_level", opts.audiences || [], prof.audience_level || ""), "audience_level")}
      ${field(t("cpLanguage"), chips("language", opts.languages || [], prof.language || ""), "language")}
      ${field(t("cpTz"), `<select class="input" id="timezone">${zones}</select>`, "timezone")}
    </form>
    ${readOnly ? "" : `<div class="save-bar"><button type="button" class="primary" id="cpSave">${escapeHtml(t("save"))}</button></div>`}
  `);
  const form = document.getElementById("cpForm");
  const backBtn = document.getElementById("cpBack");
  if (backBtn) backBtn.onclick = () => go(`chats/${id}`);
  if (readOnly) {
    form.querySelectorAll("input, textarea, select, button").forEach((node) => {
      node.disabled = true;
    });
    return;
  }
  const clearErrors = () =>
    form.querySelectorAll(".form-err").forEach((node) => {
      node.hidden = true;
    });
  form.addEventListener("input", clearErrors);
  form.querySelectorAll("[data-field]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      clearErrors();
      const name = node.getAttribute("data-field");
      form.querySelectorAll(`[data-field="${name}"]`).forEach((peer) => peer.classList.toggle("selected", peer === node));
      if (name === "niche") {
        const input = document.getElementById("niche_custom");
        input.hidden = node.getAttribute("data-value") !== "";
        if (!input.hidden) input.focus();
      }
    });
  });
  const area = document.getElementById("niche_description");
  area.addEventListener("input", () => {
    document.getElementById("descCount").textContent = String(area.value.length);
  });
  const save = document.getElementById("cpSave");
  save.onclick = () => withBusy(save, () => submit(id, seq));
}

function chosen(name) {
  const node = document.querySelector(`[data-field="${name}"].selected`);
  return node ? node.getAttribute("data-value") : null;
}

function showFieldError(name, code) {
  document.querySelectorAll(".form-err").forEach((node) => {
    node.hidden = true;
  });
  const node = document.getElementById(`err_${name}`);
  if (!node) return;
  node.textContent = t(code);
  node.hidden = false;
  node.scrollIntoView({ block: "center", behavior: "smooth" });
}

async function submit(id, seq) {
  const preset = chosen("niche");
  const body = {
    niche_code: preset === "" ? document.getElementById("niche_custom").value.trim() : preset || "",
    niche_description: document.getElementById("niche_description").value,
    tone: chosen("tone") || "",
    audience_level: chosen("audience_level") || "",
    language: chosen("language") || "",
    timezone: document.getElementById("timezone").value,
  };
  // Point at the first unanswered question before the round trip; the server still decides.
  const order = ["niche_code", "niche_description", "tone", "audience_level", "language", "timezone"];
  const missing = order.find((key) => !String(body[key]).trim());
  if (missing) {
    haptic("error");
    showFieldError(missing, missing === "niche_code" || missing === "niche_description" ? "input_empty" : "input_choice");
    return;
  }
  try {
    haptic("light");
    const data = await api(profilePath(id), { method: "PUT", body: JSON.stringify(body) });
    forget(`/api/chats/${id}`); // prefix: also drops the old form, so remember the new one after
    forget("/api/stats");
    remember(profilePath(id), data);
    haptic("success");
    toast(t("cpSaved"));
    if (current(seq)) go(`chats/${id}`);
  } catch (err) {
    haptic("error");
    const code = err && err.code;
    if (code && code.startsWith("input_")) {
      toast(t(code), "err");
      return;
    }
    toast(code === "not_owner" ? t("denied") : t("error"), "err");
  }
}
