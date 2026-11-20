import { boardChats, cached, go, haptic, load, state } from "./api.js";
import { brandHeader, current, escapeHtml, formatNumber, setBusy, setHtml, showError, skeleton, t } from "./ui.js";

const MEDALS = { 1: "🥇", 2: "🥈", 3: "🥉" };

export async function renderBoard(chatId, seq) {
  const chats = boardChats();
  const target = chatId || (chats[0] && chats[0].id) || null;
  if (!target) {
    setHtml(`
      ${brandHeader()}
      <div class="card"><div class="card-title">🏆 ${escapeHtml(t("boardTitle"))}</div>
      <p class="muted">${escapeHtml(state.dash ? t("empty") : t("loading"))}</p></div>
    `);
    return;
  }
  const path = `/api/chats/${target}/leaderboard`;
  const hit = cached(path);
  if (hit) paint(hit, chats, target);
  else setHtml(skeleton("list"));
  setBusy(true);
  try {
    const data = await load(path, { maxAge: hit ? 0 : 15000 });
    if (current(seq)) paint(data, chats, target);
  } catch (err) {
    if (current(seq) && !hit) showError(err);
  } finally {
    if (current(seq)) setBusy(false);
  }
}

function paint(data, chats, target) {
  const board = data.board || {};
  const members = board.members || [];
  const mine = board.me;
  const listed = members.some((row) => row.me);
  let rows = members.length ? members.map(boardRow).join("") : `<p class="muted empty-note">${escapeHtml(t("none"))}</p>`;
  if (mine && !listed) {
    rows += `<div class="board-gap">···</div>${boardRow({ rank: mine.rank, points: mine.points, name: t("you"), me: true })}`;
  }
  const myLine = mine
    ? `<p class="board-total muted">${escapeHtml(t("myRank", { r: mine.rank, n: board.total || members.length, c: mine.correct, a: mine.answers }))}</p>`
    : data.role === "member"
      ? `<p class="board-total muted">${escapeHtml(t("noRankYet"))}</p>`
      : "";
  const range = board.start && board.end ? `${shortDate(board.start)} – ${shortDate(board.end)}` : "";
  const picker =
    chats.length > 1
      ? `<div class="chips chips-scroll board-picker">${chats
          .map(
            (chat) =>
              `<button type="button" class="chip-btn${chat.id === target ? " selected" : ""}" data-board="${chat.id}">${escapeHtml(chat.title || "Chat")}</button>`,
          )
          .join("")}</div>`
      : "";
  setHtml(`
    ${brandHeader()}
    ${picker}
    <div class="card">
      <div class="card-title">🏆 ${escapeHtml(t("boardTitle"))}${range ? ` · ${escapeHtml(range)}` : ""}</div>
      <div class="big board-chat">${escapeHtml((data.chat && data.chat.title) || "")}</div>
      <div class="board">${rows}</div>
      ${myLine}
    </div>
  `);
  document.querySelectorAll("[data-board]").forEach((node) => {
    node.addEventListener("click", () => {
      haptic("light");
      go(`board/${node.getAttribute("data-board")}`);
    });
  });
}

function boardRow(row) {
  const medal = MEDALS[row.rank];
  const badge = medal ? `<span class="medal">${medal}</span>` : `<span class="rank-num">${row.rank}</span>`;
  const cls = `board-row${medal ? " top" : ""}${row.me ? " me" : ""}`;
  return `<div class="${cls}">
    ${badge}
    <span class="board-name">${escapeHtml(row.name)}${row.me && row.name !== t("you") ? ` <small class="muted">· ${escapeHtml(t("you"))}</small>` : ""}</span>
    <span class="board-points">${escapeHtml(formatNumber(row.points))} <small>${escapeHtml(t("points"))}</small></span>
  </div>`;
}

function shortDate(iso) {
  const match = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[3]}.${match[2]}` : String(iso);
}
