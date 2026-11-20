# M4 — Charts (Hisobot, member history, admin Statistika)

All numbers are aggregated in Postgres from real rows (posts, quizzes, quiz answers,
payments, subscriptions, usage, jobs). Telegram does not give bots view counts, so there are none.

## Endpoints

| Endpoint | Who | Notes |
|---|---|---|
| `GET /api/charts?chat=all&days=7\|30\|90` | any signed-in user | Only the chats the user manages (owner or Telegram admin); empty, zero-filled payload if none. |
| `GET /api/charts?chat=<id>&days=…` | owner, Telegram admin, super admin | Same role check as the chat panel: 404 unknown chat, 403 otherwise, 400 bad id. |
| `GET /api/me/charts?weeks=4..26` | the member | Own weekly points and accuracy only. |
| `GET /api/admin/charts?days=…` | super admin | 12 months: revenue (approved payments by review time), new trials/paid/grants, churn, active by plan, founders; daily AI usage and failed jobs. |

Day buckets use each chat's timezone (`chat_profiles.timezone`, default Asia/Tashkent);
empty days and weeks are filled with 0. Deltas compare with the previous window of the same
length (accuracy change in percentage points). Platform months use Asia/Tashkent.

## Definitions and limits

* Churn: the owner's last subscription expired in that month and no later one exists (canceled ones excluded); split after-trial vs paid.
* Founder history uses `users.founder_since`.
* Daily AI usage is recorded in `usage_daily` from migration 0011 on; earlier periods are monthly only.
* "All chats" picks "today" in the first chat's timezone; each answer is still bucketed in its own chat's timezone.
* Weekly participants are distinct users within the window (the first/last week may be partial).

## Migration 0011

`usage_daily` table, plus `ix_quiz_answers_quiz_answered (quiz_id, answered_at) INCLUDE (user_id, is_correct)`.
EXPLAIN on a 1.17M-answer dataset: per-quiz heap probes fell from ~43.8k to ~14.6k buffers and
the answer scan from 35–48 ms to 13–15 ms (90-day "all chats" request ≈ 98 ms end to end).
