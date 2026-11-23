import { applyTheme, bootstrap, go, hasRole, isManager, isStudent, isTutor, loadDash, parseRoute, prefetch, restoreSession, state, tg } from "./api.js";
import { applyRoleHint, mountRoles } from "./roles.js";
import { adminWarmPaths, renderAdmin } from "./admin.js";
import { renderBoard } from "./board.js";
import { openChat, renderChats } from "./chats.js";
import { MY_CHARTS, renderHistory } from "./history.js";
import { renderHome } from "./home.js";
import { renderChatProfile } from "./chatprofile.js";
import { renderStudy, renderStudyDetail } from "./study.js";
import { renderFeeForm } from "./fee_form.js";
import { renderNotice } from "./notice.js";
import { renderFees } from "./fees.js";
import { renderGroups } from "./groups.js";
import { renderLessons } from "./lessons.js";
import { renderReminders } from "./reminders.js";
import { renderMonth } from "./roll_month.js";
import { renderRoll } from "./roll.js";
import { renderSchedule } from "./schedule.js";
import { renderStudents } from "./students.js";
import { renderCabinet } from "./summary.js";
import { initScrollers } from "./scroller.js";
import { isProfileSub, profileWarmPaths, renderProfile, renderProfileSub } from "./profile.js";
import { chartPath, renderReport } from "./report.js";
import { bindNav, current, labelNav, navTabs, setBusy, setHtml, showError, skeleton, syncChrome, ticket } from "./ui.js";

const DASH_TTL = 20000;
let dashAt = 0;

async function boot() {
  applyTheme();
  const hinted = applyRoleHint();
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
      if (tab === "cabinet") {
        const parts = (location.hash || "").replace(/^#\/?/, "").split("/").filter(Boolean);
        const section = parts[1] || "";
        const third = parts[2] || "";
        const groupForm = section === "groups" && (third === "new" || /^\d+$/.test(third));
        const lessonForm = section === "lessons" && (third === "new" || /^\d+$/.test(third));
        const reminderForm = section === "reminders" && (third === "new" || /^\d+$/.test(third));
        const fourth = parts[3] || "";
        const studentEdit = section === "students" && /^\d+$/.test(third) && fourth === "edit";
        const studentForm =
          section === "new" ||
          /^\d+$/.test(section) ||
          (section === "students" && (third === "new" || /^\d+$/.test(third)));
        const lessonForStudent = section === "lessons" && third === "new" && /^\d+$/.test(fourth);
        if (section === "groups" && /^\d+$/.test(third) && ["topic", "attendance", "fee", "notice"].includes(fourth)) {
          go(`cabinet/groups/${third}`);
        } else if (section === "schedule" && fourth === "attendance") go("cabinet/schedule");
        else if (section === "fees") go("cabinet");
        else if (groupForm && fourth === "edit") go(`cabinet/groups/${third}`);
        else if (groupForm) go("cabinet/groups");
        else if (reminderForm) go("cabinet/reminders");
        else if (lessonForStudent) go(`cabinet/students/${fourth}`);
        else if (lessonForm) go("cabinet/lessons");
        else if (studentEdit) go(`cabinet/students/${third}`);
        else if (studentForm) go("cabinet/students");
        else if (section) go("cabinet");
        else go("profile");
        return;
      }
      if (tab === "study" || tab === "boards") {
        if (id) go("study");
        else go("profile");
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
    mountRoles();
    const { tab } = parseRoute();
    if (hinted === "student") {
      go("study");
    } else if (hinted === "teacher") {
      go("cabinet");
    } else if (isStudent() && !isTutor() && !isManager() && (tab === "home" || tab === "profile" || tab === "chats")) {
      go("study");
    } else if (tab === "home" || tab === "chats" || tab === "profile") await route({ fresh: true });
    else if (!warm) await route({ fresh: true });
    warmUp();
  } catch (err) {
    if (!warm) showError(err);
  } finally {
    setBusy(false);
  }
}

function skeletonFor(tab) {
  if (tab === "board" || tab === "report" || tab === "history" || tab === "admin" || tab === "cabinet") return "list";
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
  if (tab === "students") {
    go(sub === "new" ? "cabinet/new" : id ? `cabinet/${id}` : "cabinet");
    return;
  }
  if (!id && tab !== "history" && tab !== "cabinet" && tab !== "boards" && tab !== "study" && !navTabs().includes(tab)) {
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
  if (tab === "boards" || tab === "study") {
    if (tab === "study" && id) await renderStudyDetail(id, seq);
    else await renderStudy(seq);
    return;
  }
  if (tab === "cabinet") {
    if (!isTutor()) {
      await renderCabinet(seq);
      return;
    }
    const fourth = hashFourth();
    if (sub === "groups" && fourth === "attendance") await renderMonth(seq);
    else if (sub === "groups" && fourth === "fee") await renderFeeForm(seq);
    else if (sub === "groups" && fourth === "notice") await renderNotice(seq);
    else if (sub === "groups") await renderGroups(seq);
    else if (sub === "fees") await renderFees(seq);
    else if (sub === "schedule" && fourth === "attendance") await renderRoll(seq);
    else if (sub === "schedule") await renderSchedule(seq);
    else if (sub === "lessons") await renderLessons(seq);
    else if (sub === "reminders") await renderReminders(seq);
    else if (sub === "students" || sub === "new" || id) await renderStudents(sub, id, seq);
    else await renderCabinet(seq);
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

function hashFourth() {
  const parts = (location.hash || "").split("?")[0].replace(/^#\/?/, "").split("/").filter(Boolean);
  return parts[3] || "";
}

boot();
