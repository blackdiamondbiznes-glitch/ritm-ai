import { setLang } from "./i18n.js";
import { api, busy, esc, failed, field, head, input, loading, select, send, state, t, toast } from "./panel_kit.js";

/** Sozlamalar: what a teacher configures. Group reminders live on each group's page. */
const LANG_NAMES = { uz: "O‘zbekcha", ru: "Русский", en: "English" };

function meter(label, used, limit) {
  const cap = Number(limit) || 0;
  const share = cap ? Math.min(100, Math.round(((Number(used) || 0) / cap) * 100)) : 0;
  const text = cap ? `${used} / ${cap}` : String(used ?? 0);
  return `<div class="pd-meter"><div class="pd-meter-head"><span>${esc(label)}</span><span class="pn-num">${esc(text)}</span></div>
    ${cap ? `<progress class="pd-bar" max="${cap}" value="${Math.min(cap, Number(used) || 0)}" aria-label="${esc(label)}">${share}%</progress>` : ""}</div>`;
}

export async function renderSettings(main, parts, relabel) {
  const title = t("pnlSettings");
  loading(main, title);
  let prefs;
  let plan;
  let limits;
  let chats;
  let names;
  let groups;
  try {
    [prefs, plan, limits, chats, names, groups] = await Promise.all([
      api("/api/me/settings"),
      api("/api/plan"),
      api("/api/tutor/limits"),
      api("/api/chats").then((data) => data.chats || []),
      api("/api/tutor/summary"),
      api("/api/tutor/groups").then((data) => data.groups || []),
    ]);
  } catch (err) {
    failed(main, title, err);
    return;
  }
  const bot = state.me && state.me.bot_username;
  const botLink = bot ? `https://t.me/${bot}` : "";
  const support = prefs.support ? `https://t.me/${String(prefs.support).replace(/^@/, "")}` : "";
  const days = plan.days_left == null ? "" : t("pdDaysLeft", { n: plan.days_left });
  const chatRows = chats
    .map((chat) => `<li class="pd-member"><span class="pd-pick-text"><b>${esc(chat.title || "")}</b><small>${esc(chat.username ? `@${chat.username}` : chat.type || "")}</small></span></li>`)
    .join("");
  const groupLinks = groups.map((group) => `<li><a class="pn-link" href="#/groups/${group.id}">${esc(group.name)}</a></li>`).join("");
  main.innerHTML = `${head(title, t("pdSettingsLead"))}
    <div class="pd-settings">
      <section class="pn-card" aria-labelledby="pd-s-profile">
        <h2 id="pd-s-profile">${esc(t("pdProfile"))}</h2>
        <form class="pd-form" id="pd-name" novalidate>
          ${field(t("pdTeacherName"), input("name", names.teacher_name || "", `maxlength="64" placeholder="${esc(names.telegram_name || "")}"`), t("pdTeacherNameHint"))}
          <button type="submit" class="pn-btn pn-btn-primary">${esc(t("save"))}</button>
        </form>
      </section>
      <section class="pn-card" aria-labelledby="pd-s-region">
        <h2 id="pd-s-region">${esc(t("pdRegion"))}</h2>
        <form class="pd-form" id="pd-prefs" novalidate>
          ${field(t("pdLanguage"), select("language", (prefs.languages || []).map((code) => [code, LANG_NAMES[code] || code]), prefs.language))}
          ${field(t("pdTimezone"), select("default_timezone", (prefs.timezones || []).map((zone) => [zone, zone.replace("_", " ")]), prefs.default_timezone))}
          <button type="submit" class="pn-btn pn-btn-primary">${esc(t("save"))}</button>
        </form>
      </section>
      <section class="pn-card" aria-labelledby="pd-s-notify">
        <h2 id="pd-s-notify">${esc(t("pdNotifications"))}</h2>
        <form class="pd-form" id="pd-notify-me" novalidate>
          <label class="pd-check"><input type="checkbox" name="notify_reports"${prefs.notify_reports ? " checked" : ""}><span>${esc(t("pdNotifyReports"))}</span></label>
          <label class="pd-check"><input type="checkbox" name="notify_expiry"${prefs.notify_expiry ? " checked" : ""}><span>${esc(t("pdNotifyExpiry"))}</span></label>
          <button type="submit" class="pn-btn pn-btn-primary">${esc(t("save"))}</button>
        </form>
        <p class="pn-muted pd-small pd-gap-top">${esc(t("pdGroupReminders"))}</p>
        ${groupLinks ? `<ul class="pd-links">${groupLinks}</ul>` : ""}
      </section>
      <section class="pn-card" id="plan" aria-labelledby="pd-s-plan">
        <h2 id="pd-s-plan">${esc(t("pdPlan"))}</h2>
        <p class="pd-big">${esc(plan.plan_name || plan.plan || "")}${days ? ` <small class="pn-muted">· ${esc(days)}</small>` : ""}</p>
        ${meter(t("pnlGroups"), limits.groups && limits.groups.used, limits.groups && limits.groups.limit)}
        ${meter(t("pnlStudents"), limits.students && limits.students.used, limits.students && limits.students.limit)}
        ${meter(t("pdChats"), plan.chats_used, plan.chats_limit)}
        ${meter(t("pdAi"), plan.ai_used, plan.ai_limit)}
        ${botLink ? `<a class="pn-btn pn-btn-ghost" href="${esc(botLink)}" target="_blank" rel="noopener noreferrer">${esc(t("pdPlanInBot"))}</a>` : ""}
        <p class="pn-muted pd-small">${esc(t("pdPlanHint"))}</p>
      </section>
      <section class="pn-card" aria-labelledby="pd-s-chats">
        <h2 id="pd-s-chats">${esc(t("pdChats"))}</h2>
        ${chatRows ? `<ul class="pd-members">${chatRows}</ul>` : `<p class="pn-muted">${esc(t("pdNoChats"))}</p>`}
        <p class="pn-muted pd-small">${esc(t("pdChatsHint"))}</p>
      </section>
      <section class="pn-card" aria-labelledby="pd-s-help">
        <h2 id="pd-s-help">${esc(t("pdSupport"))}</h2>
        ${support ? `<a class="pn-btn pn-btn-ghost" href="${esc(support)}" target="_blank" rel="noopener noreferrer">${esc(t("pdWriteSupport"))}</a>` : `<p class="pn-muted">${esc(t("pdNoSupport"))}</p>`}
        <form method="post" action="/panel/logout" class="pd-gap-top"><button type="submit" class="pn-btn pn-btn-ghost">${esc(t("pnlLogout"))}</button></form>
      </section>
    </div>`;
  if (parts[0] === "plan") main.querySelector("#plan").scrollIntoView({ block: "start" });
  const nameForm = main.querySelector("#pd-name");
  nameForm.addEventListener("submit", (event) => {
    event.preventDefault();
    busy(nameForm.querySelector('[type="submit"]'), async () => {
      const saved = await send("/api/tutor/name", "POST", { name: new FormData(nameForm).get("name") });
      if (state.me) state.me.user.name = saved.teacher_name || saved.telegram_name || state.me.user.name;
      toast(t("saved"));
      relabel();
    });
  });
  const prefsForm = main.querySelector("#pd-prefs");
  prefsForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(prefsForm);
    busy(prefsForm.querySelector('[type="submit"]'), async () => {
      const language = String(data.get("language"));
      await send("/api/me/settings", "PATCH", { language, default_timezone: data.get("default_timezone") });
      if (state.me) state.me.user.language = language;
      await setLang(language);
      document.documentElement.lang = language;
      relabel();
      toast(t("saved"));
      renderSettings(main, [], relabel);
    });
  });
  const notifyForm = main.querySelector("#pd-notify-me");
  notifyForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(notifyForm);
    busy(notifyForm.querySelector('[type="submit"]'), async () => {
      await send("/api/me/settings", "PATCH", {
        notify_reports: data.get("notify_reports") === "on",
        notify_expiry: data.get("notify_expiry") === "on",
      });
      toast(t("saved"));
    });
  });
}
