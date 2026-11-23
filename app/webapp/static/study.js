import { api } from "./api.js";
import { bindJoin, joinCard } from "./join_card.js";
import { money } from "./money.js";
import { current, escapeHtml, setHtml, showError, skeleton, t } from "./ui.js";

const TZ = "Asia/Tashkent";
const MARK = {
  present: "attPresent",
  late: "attLate",
  absent: "attAbsent",
  excused: "attExcused",
};
let cache = null;

export async function renderStudy(seq) {
  setHtml(skeleton("list"));
  try {
    cache = await api("/api/me/learning");
    if (!current(seq)) return;
    paintHome(cache);
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

export async function renderStudyDetail(groupId, seq) {
  if (!cache) {
    try {
      cache = await api("/api/me/learning");
    } catch (err) {
      if (current(seq)) showError(err);
      return;
    }
  }
  if (!current(seq)) return;
  const card = (cache.groups || []).find((item) => item.group.id === Number(groupId));
  if (!card) paintHome(cache);
  else paintDetail(card);
}

function paintHome(data) {
  const pending = (data.pending || []).map(pendingCard).join("");
  const groups = (data.groups || []).map(card).join("");
  const empty = pending || groups ? "" : joinCard();
  setHtml(`
    <div class="header"><h1>${escapeHtml(t("studyNav"))}</h1><p>${escapeHtml(t("studyLead"))}</p></div>
    ${pending}${groups}${empty}
  `);
  bindJoin();
}

function card(item) {
  const group = item.group;
  const level = group.level ? ` · ${group.level}` : "";
  return `<div class="card study-card">
    <div class="card-title">${escapeHtml(group.name || "")}${escapeHtml(level)}</div>
    <div class="stu-meta">${escapeHtml(group.teacher_name || "")} · ${escapeHtml(whenDays(group))}</div>
    <div class="stu-meta">${escapeHtml(nextLine(item.next_session))}</div>
    <div class="stu-meta">${escapeHtml(t("learnAtt"))}: ${escapeHtml(percent(item.attendance))}</div>
    <div class="stu-meta">${escapeHtml(t("learnFee"))}: ${escapeHtml(feeLine(item.fee))}</div>
    <div class="stu-meta">${escapeHtml(rankLine(item.ranking))}</div>
    <a class="primary" href="#/study/${Number(group.id)}">${escapeHtml(t("learnMore"))}</a>
  </div>`;
}

function pendingCard(item) {
  return `<div class="card">
    <div class="card-title">${escapeHtml(item.group_name || "")}</div>
    <div class="stu-meta">${escapeHtml(item.teacher_name || "")}</div>
    <div class="stu-meta">${escapeHtml(t("learnPending"))}</div>
  </div>`;
}

function paintDetail(item) {
  const group = item.group;
  setHtml(`
    <div class="header"><h1>${escapeHtml(group.name || "")}</h1>
      <p>${escapeHtml(group.teacher_name || "")}</p></div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("learnRankTitle"))}</div>
      ${rankRows(item.ranking)}
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("learnScores"))}</div>
      ${scoreRows(item.scores)}
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("learnAtt"))} · ${escapeHtml(percent(item.attendance))}</div>
      ${markRows(item.attendance)}
    </div>
    <div class="card">
      <div class="card-title">${escapeHtml(t("learnHomework"))}</div>
      ${homeworkRows(item.homework)}
    </div>
  `);
}

function homeworkRows(rows) {
  if (!rows || !rows.length) return `<div class="stu-meta">${escapeHtml(t("learnNoHw"))}</div>`;
  return rows
    .map((item) => {
      const due = item.due_on ? ` · ${t("learnHwDue", { when: dayMonth(item.due_on) })}` : "";
      return `<div class="stu-row"><div>
        <div class="chat-name">${escapeHtml(item.topic || "")}</div>
        <div class="stu-meta">${escapeHtml(item.text || "")}${escapeHtml(due)}</div>
      </div></div>`;
    })
    .join("");
}

function rankRows(ranking) {
  if (!ranking || !ranking.length) return `<div class="stu-meta">${escapeHtml(t("rankEmpty"))}</div>`;
  return ranking
    .map((item) => {
      const mine = item.mine ? " stu-paid" : "";
      return `<div class="stu-row${mine}"><div class="chat-name">${item.rank}. ${escapeHtml(item.name || "")}</div><span>${item.total}</span></div>`;
    })
    .join("");
}

function scoreRows(scores) {
  if (!scores || !scores.length) return `<div class="stu-meta">${escapeHtml(t("learnNoScore"))}</div>`;
  return scores
    .map(
      (item) =>
        `<div class="stu-row"><div class="chat-name">${escapeHtml(item.topic || "")}</div><span>${item.score}</span></div>`,
    )
    .join("");
}

function markRows(attendance) {
  const rows = (attendance && attendance.last) || [];
  if (!rows.length) return `<div class="stu-meta">${escapeHtml(t("attNone"))}</div>`;
  return rows
    .map((item) => {
      const label = t(MARK[item.status] || "attNone");
      return `<div class="stu-row"><div class="chat-name">${escapeHtml(stamp(item.starts_at))}</div><span>${escapeHtml(label)}</span></div>`;
    })
    .join("");
}

function nextLine(session) {
  if (!session || !session.starts_at) return t("learnNoLesson");
  return t("learnNext", { when: stamp(session.starts_at) });
}

function feeLine(fee) {
  if (!fee) return t("learnFeeNone");
  if (fee.status === "paid" || fee.status === "waived") return t("learnPaid");
  if (fee.lessons_total != null) return t("learnPack", { used: fee.lessons_used || 0, total: fee.lessons_total });
  if (fee.amount == null) return t("learnFeeNone");
  return t("learnDue", { amount: money(fee.amount), when: dayMonth(fee.due_on) });
}

function rankLine(ranking) {
  const mine = (ranking || []).find((item) => item.mine);
  if (!mine) return t("learnNoRank");
  return t("learnRank", { rank: mine.rank, size: ranking.length });
}

function percent(attendance) {
  const rate = attendance && attendance.rate;
  if (rate == null) return "—";
  return `${Math.round(rate * 100)}%`;
}

function whenDays(group) {
  const days = (group.weekdays || []).map((day) => t(`day${day}`)).join(", ");
  return `${days} · ${group.start}–${group.end}`;
}

function stamp(iso) {
  if (!iso) return "";
  const parts = partsOf(iso);
  return `${parts.day}-${t(`learnM${parts.month}`)} ${parts.time}`;
}

function dayMonth(iso) {
  if (!iso || iso.length < 10) return "";
  const month = Number(iso.slice(5, 7));
  const day = Number(iso.slice(8, 10));
  return `${day}-${t(`learnM${month}`)}`;
}

function partsOf(iso) {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    day: "numeric",
    month: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const bag = {};
  for (const part of fmt.formatToParts(new Date(iso))) bag[part.type] = part.value;
  return { day: Number(bag.day), month: Number(bag.month), time: `${bag.hour}:${bag.minute}` };
}
