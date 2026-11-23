import { applyTheme, bootstrap, go, hasRole, isManager, isTutor, loadDash, parseRoute, prefetch, restoreSession, state, tg } from "./api.js";
import { applyRoleHint, studentMode } from "./roles.js";
import { initScrollers } from "./scroller.js";
import { bindNav, labelNav, navTabs, syncChrome } from "./nav.js";
import { current, setBusy, setHtml, showError, skeleton, ticket } from "./ui.js";

const DASH_TTL = 20000;
let dashAt = 0;

const loaders = {
  admin: () => import("./admin.js"),
  board: () => import("./board.js"),
  chats: () => import("./chats.js"),
  history: () => import("./history.js"),
  home: () => import("./home.js"),
  chatprofile: () => import("./chatprofile.js"),
  study: () => import("./study.js"),
  fee_form: () => import("./fee_form.js"),
  notice: () => import("./notice.js"),
  fees: () => import("./fees.js"),
  groups: () => import("./groups.js"),
  lessons: () => import("./lessons.js"),
  reminders: () => import("./reminders.js"),
  roll_month: () => import("./roll_month.js"),
  roll: () => import("./roll.js"),
  schedule: () => import("./schedule.js"),
  students: () => import("./students.js"),
  reports: () => import("./reports.js"),
  summary: () => import("./summary.js"),
  profile: () => import("./profile.js"),
  report: () => import("./report.js"),
};


async function boot() {
  // The teacher web panel frames cabinet screens: hide the Mini App bottom bar there.
  if (window.top !== window.self && new URLSearchParams(location.search).has("embed")) {
    document.documentElement.classList.add("embed");
  }
  applyTheme();
  const hinted = applyRoleHint();
  const warm = restoreSession();
  bindNav();
  initScrollers(document.getElementById("main"));
  if (!location.hash) history.replaceState(null, "", "#/home");
  window.addEventListener("hashchange", () => {
    route().catch((err) => showError(err, () => route({ fresh: true })));
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
        // Cabinet root is home: keep the user here (BackButton is hidden).
        return;
      }
      if (tab === "study" || tab === "boards") {
        if (id) go("study");
        return;
      }
      if ((tab === "board" || tab === "history") && studentMode()) {
        go("profile");
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
    const student = studentMode();
    const atHome = tab === "home" || location.hash === "#/cabinet";
    if (hinted === "student") {
      go("study");
    } else if (hinted === "teacher" || (isTutor() && !student && atHome)) {
      go("cabinet");
    } else if (student && (tab === "home" || (tab === "chats" && !isManager()))) {
      go("study");
    } else if (tab === "home" || tab === "chats" || tab === "profile") await route({ fresh: true });
    else if (!warm) await route({ fresh: true });
    warmUp();
  } catch (err) {
    if (!warm) showError(err, () => boot());
  } finally {
    setBusy(false);
    const splash = document.getElementById("boot");
    if (splash) splash.hidden = true;
  }
}

function skeletonFor(tab) {
  if (["board", "report", "history", "admin", "cabinet", "agenda"].includes(tab)) return "list";
  return "home";
}

async function warmUp() {
  const chats = (state.dash && state.dash.chats) || [];
  const paths = [];
  const member = state.dash && state.dash.member;
  const { tab } = parseRoute();
  if (member && (tab === "history" || tab === "board" || tab === "home")) {
    const history = await loaders.history();
    paths.push("/api/me/stats", history.MY_CHARTS);
    (member.chats || []).slice(0, 2).forEach((chat) => paths.push(`/api/chats/${chat.id}/leaderboard`));
  }
  if (tab === "chats" || tab === "home" || tab === "report" || tab === "board") {
    chats.slice(0, 3).forEach((chat) => {
      paths.push(`/api/chats/${chat.id}/leaderboard`, `/api/chats/${chat.id}`);
    });
    if (chats[0] && (tab === "report" || tab === "home")) {
      const report = await loaders.report();
      paths.push(report.chartPath("all"));
    }
  }
  if (studentMode() && (tab === "study" || tab === "agenda" || tab === "profile")) {
    const study = await loaders.study();
    paths.push(...study.STUDY_PATHS);
  }
  if (tab === "profile") {
    const profile = await loaders.profile();
    paths.push(...profile.profileWarmPaths());
  }
  if (hasRole("super_admin") && tab === "admin") {
    const admin = await loaders.admin();
    paths.push(...admin.adminWarmPaths());
  }
  if (paths.length) prefetch(paths);
}

async function route(opts = {}) {
  const seq = ticket();
  const { tab, sub, id } = parseRoute();
  if (tab === "home" && (isTutor() || studentMode())) {
    go(studentMode() ? "study" : "cabinet");
    return;
  }
  if (tab === "students") {
    go(sub === "new" ? "cabinet/new" : id ? `cabinet/${id}` : "cabinet");
    return;
  }
  const linked = tab === "history" || (tab === "board" && hasRole("member"));
  if (!id && !linked && tab !== "cabinet" && tab !== "boards" && tab !== "study" && !navTabs().includes(tab)) {
    go("home");
    return;
  }
  syncChrome();
  window.scrollTo(0, 0);
  if (tab === "chats" && sub === "edit" && id) {
    await (await loaders.chatprofile()).renderChatProfile(id, seq);
    return;
  }
  if (tab === "chats" && id) {
    await (await loaders.chats()).openChat(id, seq);
    return;
  }
  if (tab === "profile" && sub) {
    if (!(await loaders.profile()).isProfileSub(sub)) {
      go("profile");
      return;
    }
    await (await loaders.profile()).renderProfileSub(sub, seq);
    return;
  }
  if (tab === "board") {
    await (await loaders.board()).renderBoard(id, seq);
    return;
  }
  if (tab === "report") {
    await (await loaders.report()).renderReport(id, seq);
    return;
  }
  if (tab === "history") {
    await (await loaders.history()).renderHistory(seq);
    return;
  }
  if (tab === "admin") {
    await (await loaders.admin()).renderAdmin(sub, id, seq);
    return;
  }
  if (tab === "agenda") {
    await (await loaders.study()).renderAgenda(seq);
    return;
  }
  if (tab === "boards" || tab === "study") {
    if (tab === "study" && id) await (await loaders.study()).renderStudyDetail(id, seq);
    else await (await loaders.study()).renderStudy(seq);
    return;
  }
  if (tab === "cabinet") {
    if (!isTutor()) {
      await (await loaders.summary()).renderCabinet(seq);
      return;
    }
    const fourth = hashFourth();
    if (sub === "groups" && fourth === "attendance") await (await loaders.roll_month()).renderMonth(seq);
    else if (sub === "groups" && fourth === "fee") await (await loaders.fee_form()).renderFeeForm(seq);
    else if (sub === "groups" && fourth === "notice") await (await loaders.notice()).renderNotice(seq);
    else if (sub === "groups") await (await loaders.groups()).renderGroups(seq);
    else if (sub === "fees") await (await loaders.fees()).renderFees(seq);
    else if (sub === "schedule" && fourth === "attendance") await (await loaders.roll()).renderRoll(seq);
    else if (sub === "schedule") await (await loaders.schedule()).renderSchedule(seq);
    else if (sub === "lessons") await (await loaders.lessons()).renderLessons(seq);
    else if (sub === "reminders") await (await loaders.reminders()).renderReminders(seq);
    else if (sub === "reports") await (await loaders.reports()).renderReports(seq);
    else if (sub === "students" || sub === "new" || id) await (await loaders.students()).renderStudents(sub, id, seq);
    else await (await loaders.summary()).renderCabinet(seq);
    return;
  }
  const paint = async () => {
    if (tab === "chats") (await loaders.chats()).renderChats();
    else if (tab === "profile") (await loaders.profile()).renderProfile();
    else (await loaders.home()).renderHome();
  };
  if (state.dash) await paint();
  else setHtml(skeleton("home"));
  if (opts.fresh || !state.me) return;
  if (Date.now() - dashAt < DASH_TTL && state.dash) return;
  setBusy(true);
  try {
    await loadDash();
    dashAt = Date.now();
    if (current(seq)) await paint();
  } catch (err) {
    if (current(seq) && !state.dash) showError(err, () => route({ fresh: true }));
  } finally {
    if (current(seq)) setBusy(false);
  }
}

function hashFourth() {
  const parts = (location.hash || "").split("?")[0].replace(/^#\/?/, "").split("/").filter(Boolean);
  return parts[3] || "";
}

boot();
