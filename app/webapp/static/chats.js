import { RESULT } from "./i18n.js";
import { api, cached, forget, go, haptic, load, remember, state, tg } from "./api.js";
import { profileLabels, profilePath } from "./chatprofile.js";
import { withPlan } from "./home.js";
import {
  bindPickers,
  brandHeader,
  roleBadge,
  chatCard,
  current,
  escapeHtml,
  fieldChecked,
  fieldValue,
  scheduleBlock,
  section,
  setBusy,
  setHtml,
  showError,
  skeleton,
  t,
  toast,
  toggleField,
  weekdayChips,
  withBusy,
} from "./ui.js";

export function renderChats() {
  const dash = state.dash || { chats: [], plan: {} };
  const chats = dash.chats || [];
  const plan = dash.plan || {};
  setHtml(`
    ${brandHeader()}
    <h2 class="page-title">${escapeHtml(t("chats"))}</h2>
    ${
      chats.length
        ? chats.map((chat) => chatCard(withPlan(chat, plan), `data-go="${chat.id}"`)).join("")
        : `<div class="card muted">${escapeHtml(t("empty"))}</div>`
    }
    <button type="button" class="ghost wide" id="connectChat">➕ ${escapeHtml(t("rowConnect"))}</button>
  `);
  document.getElementById("connectChat").onclick = () => {
    haptic("light");
    go("profile/connect");
  };
  document.querySelectorAll("[data-go]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(`chats/${node.getAttribute("data-go")}`);
    });
  });
}

export async function openChat(id, seq) {
  const path = `/api/chats/${id}`;
  const hit = cached(path);
  if (hit) renderChat(hit, "");
  else setHtml(skeleton("chat"));
  const hadForm = Boolean(cached(profilePath(id)));
  setBusy(true);
  try {
    const detail = await load(path, { maxAge: 0 });
    if (current(seq)) renderChat(detail, "");
    if (!hadForm && detail.profile) {
      // Labels for the profile summary come from the wizard options; repaint once they arrive.
      load(profilePath(id))
        .then(() => {
          if (current(seq) && !document.activeElement?.closest("#settings")) renderChat(cached(path) || detail, "");
        })
        .catch(() => {});
    }
  } catch (err) {
    if (current(seq) && !hit) showError(err);
  } finally {
    if (current(seq)) setBusy(false);
  }
}

export function renderChat(detail, note) {
  const chat = detail.chat;
  const profile = detail.profile;
  const daily = detail.daily || { time: "09:00", enabled: false };
  const quiz = detail.quiz || { time: "09:00", enabled: false };
  const board = detail.leaderboard || { time: "09:00", enabled: false, weekday: 1 };
  const mods = detail.modules || {};
  const locked = (label) => `<p class="locked">🔒 ${escapeHtml(label)}: ${escapeHtml(t("module"))}</p>`;
  const labels = profileLabels(chat.id, profile);
  const profileFacts = profile
    ? `<p>${escapeHtml(labels ? labels.niche : profile.niche_code)} · ${escapeHtml(labels ? labels.language : profile.language)} · ${escapeHtml(profile.timezone)}</p>
       <p class="muted">${escapeHtml(labels ? labels.tone : profile.tone)} · ${escapeHtml(labels ? labels.audience : profile.audience_level)}</p>`
    : `<p class="muted">${escapeHtml(t("profileNeed"))}</p>`;
  const profileHtml = `${profileFacts}<button type="button" class="ghost wide keep" id="editProfile">✏️ ${escapeHtml(profile ? t("cpEdit") : t("cpFill"))}</button>`;
  const quizBody = mods.quiz ? scheduleBlock("quiz", t("quiz"), quiz, true) : locked(t("quiz"));
  const apqBody = mods.admin_post_quiz
    ? `<div class="sub-block">
        <div class="sub-title">🧩 ${escapeHtml(t("apq"))}</div>
        ${toggleField("admin_post_quiz", mods.admin_post_quiz_on, t("apqOn"), t("apqOff"), t("apqHint"))}
      </div>`
    : "";
  const boardBody = mods.leaderboard
    ? `${scheduleBlock("board", t("board"), board, true)}${weekdayChips(board.weekday || 1)}`
    : locked(t("board"));
  // Older cached payloads have no access block: treat them as owner views; the server decides anyway.
  const access = detail.access || { role: "owner", can_edit: true, can_act: true, can_manage_admins: true };
  const readOnly = !access.can_edit;
  const members = chat.member_count != null ? `<span class="pill">${escapeHtml(t("members", { n: chat.member_count }))}</span>` : "";
  setHtml(`
    <div class="header"><h1>${escapeHtml(chat.title)}</h1>
      <div class="header-pills">${roleBadge(access.role)}<span class="pill">${escapeHtml(t("statusOn"))}</span>${members}</div>
    </div>
    ${note ? `<p class="ok note">${escapeHtml(note)}</p>` : ""}
    ${readOnly ? `<div class="readonly-note">🔒 ${escapeHtml(t("readOnly"))}</div>` : ""}
    <div id="settings"${readOnly ? ' class="readonly"' : ""}>
      ${section("👤", t("profile"), profileHtml)}
      ${section("📝", t("daily"), scheduleBlock("daily", t("daily"), daily, true))}
      ${section("🎯", t("quiz"), quizBody + apqBody)}
      ${section("🏆", t("board"), boardBody)}
      ${
        access.can_manage_admins
          ? section(
              "👥",
              t("adminsTitle"),
              toggleField("admins_can_edit", access.admins_can_edit, t("adminsEditOn"), t("adminsEditOff"), t("adminsEditHint")),
            )
          : ""
      }
    </div>
    ${
      readOnly
        ? ""
        : `<div class="save-bar">
      <button type="button" class="primary" id="save">${escapeHtml(t("save"))}</button>
    </div>`
    }
    ${access.can_act ? section(
      "⚡",
      t("quick"),
      `<p class="muted small-text">${escapeHtml(t("quickHint"))}</p>
       <div class="row quick" data-busy-group>
        <button type="button" class="ghost" id="postNow">📝 ${escapeHtml(t("postNow"))}</button>
        ${mods.quiz ? `<button type="button" class="ghost" id="quizNow">🎯 ${escapeHtml(t("quizNow"))}</button>` : ""}
        ${mods.leaderboard ? `<button type="button" class="ghost" id="boardNow">🏆 ${escapeHtml(t("boardNow"))}</button>` : ""}
      </div>`,
      "quick-card",
    ) : ""}
    ${
      access.role === "owner" || access.role === "super"
        ? section(
            "🔌",
            t("dangerTitle"),
            `<p class="muted small-text">${escapeHtml(t("dangerHint"))}</p>
             <button type="button" class="danger wide-btn" id="disconnect">${escapeHtml(t("dangerTitle"))}</button>`,
            "danger-card",
          )
        : ""
    }
  `);
  if (readOnly) {
    document.querySelectorAll("#settings input, #settings button:not(.keep)").forEach((node) => {
      node.disabled = true;
    });
  }
  const save = document.getElementById("save");
  if (save) save.onclick = () => withBusy(save, () => saveChat(chat.id));
  const post = document.getElementById("postNow");
  if (post) post.onclick = () => withBusy(post, () => runNow(chat.id, "post-now"));
  const quizBtn = document.getElementById("quizNow");
  if (quizBtn) quizBtn.onclick = () => withBusy(quizBtn, () => runNow(chat.id, "quiz-now"));
  const boardBtn = document.getElementById("boardNow");
  if (boardBtn) boardBtn.onclick = () => withBusy(boardBtn, () => runNow(chat.id, "board-now"));
  const edit = document.getElementById("editProfile");
  if (edit) {
    edit.onclick = () => {
      haptic("light");
      go(`chats/edit/${chat.id}`);
    };
  }
  const off = document.getElementById("disconnect");
  if (off) off.onclick = () => askThen(t("dangerAsk"), () => withBusy(off, () => disconnect(chat.id)));
  bindPickers();
}

function askThen(text, then) {
  if (tg && tg.showConfirm && (!tg.isVersionAtLeast || tg.isVersionAtLeast("6.2"))) {
    tg.showConfirm(text, (ok) => {
      if (ok) then();
    });
    return;
  }
  if (window.confirm(text)) then();
}

async function disconnect(id) {
  try {
    haptic("medium");
    await api(`/api/chats/${id}/disconnect`, { method: "POST" });
    forget(`/api/chats/${id}`);
    forget("/api/stats");
    forget("/api/connect");
    if (state.dash && state.dash.chats) state.dash.chats = state.dash.chats.filter((chat) => chat.id !== id);
    haptic("success");
    toast(t("dangerDone"));
    go("chats");
  } catch (err) {
    haptic("error");
    toast(errorText(err), "err");
  }
}

async function saveChat(id) {
  const body = {
    daily_time: fieldValue("daily_time"),
    daily_enabled: fieldChecked("daily_enabled"),
    quiz_time: fieldValue("quiz_time"),
    quiz_enabled: fieldChecked("quiz_enabled"),
    board_time: fieldValue("board_time"),
    board_enabled: fieldChecked("board_enabled"),
  };
  const weekday = fieldValue("board_weekday");
  if (weekday) body.board_weekday = Number(weekday);
  const apq = document.getElementById("admin_post_quiz");
  if (apq && apq.checked !== apq.defaultChecked) body.admin_post_quiz = apq.checked;
  const delegate = document.getElementById("admins_can_edit");
  if (delegate && delegate.checked !== delegate.defaultChecked) body.admins_can_edit = delegate.checked;
  try {
    haptic("light");
    const detail = await api(`/api/chats/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    remember(`/api/chats/${id}`, detail);
    forget(`/api/chats/${id}/`);
    haptic("success");
    renderChat(detail, "");
    toast(t("saved"));
  } catch (err) {
    haptic("error");
    toast(errorText(err), "err");
  }
}

async function runNow(id, kind) {
  try {
    haptic("medium");
    const data = await api(`/api/chats/${id}/${kind}`, { method: "POST" });
    const key = data.result === "empty" ? "boardEmpty" : RESULT[data.result] || "error";
    toast(t(key), data.result === "queued" ? "ok" : "err");
    if (data.result === "queued") haptic("success");
  } catch (err) {
    haptic("error");
    toast(errorText(err), "err");
  }
}

function errorText(err) {
  if (err && err.code === "not_owner") return t("denied");
  if (err && err.code === "owner_only") return t("ownerOnly");
  if (err && err.code === "profile") return t("profileNeed");
  if (err && err.code === "module") return t("module");
  if (err && err.code === "rate_limit") return t("slowDown");
  return t("error");
}
