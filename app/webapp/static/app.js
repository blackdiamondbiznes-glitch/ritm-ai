import { applyTheme, bootstrap, go, hasRole, loadDash, parseRoute, prefetch, restoreSession, state, tg } from "./api.js";
import { adminWarmPaths, renderAdmin } from "./admin.js";
import { renderBoard } from "./board.js";
import { openChat, renderChats } from "./chats.js";
import { MY_CHARTS, renderHistory } from "./history.js";
import { renderHome } from "./home.js";
import { renderChatProfile } from "./chatprofile.js";
import { initScrollers } from "./scroller.js";
import { isProfileSub, profileWarmPaths, renderProfile, renderProfileSub } from "./profile.js";
import { chartPath, renderReport } from "./report.js";
import { bindNav, current, labelNav, navTabs, setBusy, setHtml, showError, skeleton, syncChrome, ticket } from "./ui.js";

const DASH_TTL = 20000;
let dashAt = 0;

async function boot() {
  applyTheme();
  const warm = restoreSession();
  bindNav();
  initScrollers(document.getElementById("main"));
  if (!location.hash) history.replaceState(null, "", "#/home");
  window.addEventListener("hashchange", () => {
    route().catch(showError);
  });
  if (tg && tg.BackButton && tg.BackButton.onClick) {
    tg.BackButton.onClick(() => {
      const { tab, sub, id } = parseRoute();
      if (tab === "admin") {
        if (sub === "tenant") go("admin/tenants");
        else if (sub === "pay") go("admin/payments");
        else go(sub && !id ? "admin" : "home");
        return;
      }
      if (tab === "chats" && sub === "edit" && id) go(`chats/${id}`);
      else if (tab === "profile" && sub) go("profile");
      else go(tab === "chats" || tab === "report" ? tab : "home");
    });
  }
  if (warm) route({ fresh: true }).catch(() => {});
  else setHtml(skeleton(skeletonFor(parseRoute().tab)));
  setBusy(true);
  try {
    await bootstrap();
    dashAt = Date.now();
    labelNav();
    syncChrome();
    const { tab } = parseRoute();
    if (tab === "home" || tab === "chats" || tab === "profile") await route({ fresh: true });
    else if (!warm) await route({ fresh: true });
    warmUp();
  } catch (err) {
    if (!warm) showError(err);
  } finally {
    setBusy(false);
  }
}

function skeletonFor(tab) {
  if (tab === "board" || tab === "report" || tab === "history" || tab === "admin") return "list";
  return "home";
}

function warmUp() {
  const chats = (state.dash && state.dash.chats) || [];
  const paths = [];
  const member = state.dash && state.dash.member;
  if (member) {
    paths.push("/api/me/stats", MY_CHARTS);
    (member.chats || []).slice(0, 2).forEach((chat) => paths.push(`/api/chats/${chat.id}/leaderboard`));
  }
  chats.slice(0, 3).forEach((chat) => {
    paths.push(`/api/chats/${chat.id}/leaderboard`, `/api/chats/${chat.id}`);
  });
  if (chats[0]) paths.push(chartPath("all"));
  paths.push(...profileWarmPaths());
  if (hasRole("super_admin")) paths.push(...adminWarmPaths());
  prefetch(paths);
}

async function route(opts = {}) {
  const seq = ticket();
  const { tab, sub, id } = parseRoute();
  if (!id && tab !== "history" && !navTabs().includes(tab)) {
    go("home");
    return;
  }
  syncChrome();
  window.scrollTo(0, 0);
  if (tab === "chats" && sub === "edit" && id) {
    await renderChatProfile(id, seq);
    return;
  }
  if (tab === "chats" && id) {
    await openChat(id, seq);
    return;
  }
  if (tab === "profile" && sub) {
    if (!isProfileSub(sub)) {
      go("profile");
      return;
    }
    await renderProfileSub(sub, seq);
    return;
  }
  if (tab === "board") {
    await renderBoard(id, seq);
    return;
  }
  if (tab === "report") {
    await renderReport(id, seq);
    return;
  }
  if (tab === "history") {
    await renderHistory(seq);
    return;
  }
  if (tab === "admin") {
    await renderAdmin(sub, id, seq);
    return;
  }
  const paint = () => {
    if (tab === "chats") renderChats();
    else if (tab === "profile") renderProfile();
    else renderHome();
  };
  if (state.dash) paint();
  else setHtml(skeleton("home"));
  if (opts.fresh || !state.me) return;
  if (Date.now() - dashAt < DASH_TTL && state.dash) return;
  setBusy(true);
  try {
    await loadDash();
    dashAt = Date.now();
    if (current(seq)) paint();
  } catch (err) {
    if (current(seq) && !state.dash) showError(err);
  } finally {
    if (current(seq)) setBusy(false);
  }
}

boot();
