# Running Ritm AI on Render

One Docker **web service** runs everything on Render's single public port (`$PORT`):
the bot, the Mini App (`/`, `/api/*`, `/s/*`), the health check (`/health`) and, in webhook
mode, the Telegram webhook (`/tg/<secret>`). Data lives in **Render Postgres**.
`render.yaml` describes both resources.

## Settings that matter on Render

| Variable | Value on Render | Why |
|---|---|---|
| `TELEGRAM_MODE` | `off` before cutover, `webhook` after | `off`: Mini App + health only, no updates, no scheduled jobs (safe while another copy polls). `webhook`: Telegram pushes updates. `polling` is for local Docker |
| `DATABASE_URL` | Render's internal connection string | `postgres://` / `postgresql://` become `postgresql+asyncpg://`; `sslmode=` becomes asyncpg `ssl=` |
| `HEALTH_PORT` | `0` | health is served on `$PORT` at `/health` |
| `PORT`, `RENDER_EXTERNAL_URL` | set by Render | Mini App binds `$PORT`; the menu button and webhook use the onrender.com URL unless `WEBAPP_URL` (custom domain) is set |
| `WEBHOOK_SECRET` | optional | path + `X-Telegram-Bot-Api-Secret-Token`; derived from `BOT_TOKEN` when empty |

In webhook mode the process calls `setWebhook` (pending updates kept), and in polling mode it
calls `deleteWebhook` first, so switching back to local Docker removes the Render webhook.
**Never run two copies with Telegram enabled at the same time.**

## Free vs paid

Free web service: sleeps after 15 minutes without inbound HTTP and takes about a minute to
wake. A Telegram webhook request wakes it (Telegram retries and keeps updates for up to 24 h),
but **scheduled jobs (daily posts, quizzes, leaderboards, trial reminders, payment-draft
expiry) do not run while it sleeps**. The in-memory FSM state and pending chat invites are
lost whenever it sleeps or restarts. 750 free instance hours per workspace per month.

Free Postgres: 1 GB, no backups, one per workspace, **expires 30 days after creation**
(14-day grace to upgrade, then deleted). The bot itself sends a daily `pg_dump` to every
super admin in Telegram at 04:00 Asia/Tashkent (see README, `BACKUP_*`).

Production: web service `0.5c-512mb` ($7/month) + Postgres `0.1c-256mb` ($6/month, storage
$0.30/GB) on the Hobby workspace ($0) — about $13/month.

## Cutover from local Docker

1. Deploy on Render with `TELEGRAM_MODE=off`; check `https://<service>.onrender.com/health`.
2. Stop the local bot: `docker compose stop bot` (Postgres keeps running).
3. Dump: `docker compose exec -T postgres pg_dump -U bot -d engagement -Fc > backups/cutover.dump`.
4. Temporarily allow the machine's public IP on the Render database (Access Control / API
   `ipAllowList`), then restore:
   `docker run --rm -v ./backups:/b postgres:16-alpine pg_restore --clean --if-exists --no-owner --no-acl -d "<external URL>?sslmode=require" /b/cutover.dump`.
   Remove the IP from the allow list afterwards.
5. Set `TELEGRAM_MODE=webhook` on Render and redeploy. The bot sets the webhook, the menu
   button (Mini App on the onrender.com URL) and the commands.
6. Check `getWebhookInfo` (no `last_error_message`), `/start`, and the Mini App.

Rollback: set `TELEGRAM_MODE=off` on Render, then start the local bot (polling deletes the
webhook). Data written on Render after cutover is not in the local database.
