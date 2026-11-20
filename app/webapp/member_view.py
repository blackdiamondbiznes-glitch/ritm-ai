"""What a regular quiz participant sees: their own points, ranks and answers."""

from __future__ import annotations

from typing import Any

from app.db.models.chats import Chat
from app.webapp.panel import ROLE_ADMIN, ROLE_OWNER

HISTORY_LIMIT = 20


async def member_chats(ctx) -> list[tuple[Chat, dict[str, Any]]]:
    """Active chats where the user has answered at least one quiz, newest activity first."""
    if "member_chats" in ctx.memo:
        return ctx.memo["member_chats"]
    totals = await ctx.engagement.member_totals(ctx.user.id)
    rows: list[tuple[Chat, dict[str, Any]]] = []
    if totals:
        chats = await ctx.panel.chats.get_by_ids(list(totals))
        rows = [(chat, totals[chat.id]) for chat in chats if chat.is_active]
        rows.sort(key=lambda item: _stamp(item[1].get("last_at")), reverse=True)
    ctx.memo["member_chats"] = rows
    return rows


async def resolve_roles(ctx) -> list[str]:
    """Server-side roles for the signed-in user. Order is stable for the client."""
    if "roles" in ctx.memo:
        return ctx.memo["roles"]
    roles: list[str] = []
    if ctx.is_super:
        roles.append("super_admin")
    managed = await ctx.panel.managed(ctx.user)
    if any(role == ROLE_OWNER for _chat, role in managed):
        roles.append("owner")
    if any(role == ROLE_ADMIN for _chat, role in managed):
        roles.append("admin")
    if await member_chats(ctx):
        roles.append("member")
    ctx.memo["roles"] = roles
    return roles


async def member_summary(ctx, *, history: bool = False) -> dict[str, Any] | None:
    """Points, weekly rank and accuracy per chat. None when the user never answered."""
    rows = await member_chats(ctx)
    if not rows:
        return None
    points_each = int(ctx.settings.points_per_correct_answer)
    chats: list[dict[str, Any]] = []
    all_answers = all_correct = week_points = 0
    for chat, totals in rows:
        profile = await ctx.panel.profiles.get(chat.id)
        zone = profile.timezone if profile is not None else ctx.settings.default_timezone
        board = await ctx.panel.leaderboard.live(chat, zone)
        mine = next((row for row in board.members if row.telegram_id == ctx.user.telegram_id), None)
        answers = int(totals["answers"])
        correct = int(totals["correct"])
        all_answers += answers
        all_correct += correct
        item: dict[str, Any] = {
            "id": chat.id,
            "title": chat.title,
            "answers": answers,
            "correct": correct,
            "accuracy": _pct(correct, answers),
            "points_total": correct * points_each,
            "week_members": len(board.members),
            "week_points": 0,
            "week_rank": None,
        }
        if mine is not None:
            item["week_points"] = mine.score.points
            item["week_rank"] = mine.rank
            week_points += mine.score.points
        chats.append(item)
    data: dict[str, Any] = {
        "chats": chats,
        "totals": {
            "answers": all_answers,
            "correct": all_correct,
            "accuracy": _pct(all_correct, all_answers),
            "points_total": all_correct * points_each,
            "week_points": week_points,
        },
    }
    if history:
        titles = {chat.id: chat.title for chat, _totals in rows}
        items = await ctx.engagement.member_history(ctx.user.id, HISTORY_LIMIT)
        missing = [row["chat_id"] for row in items if row["chat_id"] not in titles]
        if missing:
            for chat in await ctx.panel.chats.get_by_ids(sorted(set(missing))):
                titles[chat.id] = chat.title
        data["history"] = [
            {
                "chat_id": row["chat_id"],
                "chat_title": titles.get(row["chat_id"], ""),
                "question": row["question"],
                "chosen": row["chosen"],
                "correct": row["correct"],
                "is_correct": row["is_correct"],
                "answered_at": row["answered_at"].isoformat() if row["answered_at"] else None,
            }
            for row in items
        ]
    return data


def _pct(part: int, whole: int) -> int | None:
    if whole <= 0:
        return None
    return round(part * 100 / whole)


def _stamp(value: object) -> float:
    return value.timestamp() if hasattr(value, "timestamp") else 0.0
