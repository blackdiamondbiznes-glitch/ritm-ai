# Ritm AI

Ritm is a Telegram-first platform for businesses and communities that work through Telegram. It starts with online teaching, while its community tools help any group or channel keep its audience active.
The Telegram bot is `@ritm_airobot`; the Mini App and teacher panel provide role-specific workspaces over the same platform.
Phase 1 is onboarding and access. Phase 2 adds AI, the queue and a daily post. Phase 3 adds a quiz from published posts: a private deep link in channels, a native poll in groups. Phase 4 adds automatic quizzes from an admin's own posts. Phase 5 adds points for correct quiz answers and a weekly Top-10 leaderboard. Phase 6 adds manual card payments, founder pricing, trial engagement reports and an expiry notice. Phase 7 hardens the bot: backups, a health check, error alerts, structured logs and a production deploy guide.

## Run

```bash
cp .env.example .env
# put the real bot token and your Telegram id into SUPER_ADMIN_IDS
docker compose up --build
```

`docker-compose.override.yml` publishes Postgres on port 5432 for local development.
Production should use only the base file, which does not publish the database port:

```bash
docker compose -f docker-compose.yml up --build -d
```

The container runs `alembic upgrade head` before the bot process. The bot uses long polling.

## Environment

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `BOT_TOKEN` | yes | | Telegram bot token |
| `DATABASE_URL` | yes | | `postgresql+asyncpg://...` |
| `SUPER_ADMIN_IDS` | no | empty | Comma-separated Telegram ids |
| `TRIAL_DAYS` | no | `5` | Length of the first-chat trial |
| `THROTTLE_SECONDS` | no | `0.5` | Minimum gap between updates per user |
| `DEFAULT_TIMEZONE` | no | `Asia/Tashkent` | Suggested profile timezone |
| `LOG_LEVEL` | no | `INFO` | Standard logging level |
| `AI_PROVIDER` | no | `gemini` | `gemini` or `openai` |
| `GEMINI_API_KEY` | for Gemini | empty | Google AI key. Sent as a header, never logged |
| `GEMINI_MODEL` | no | `gemini-3.6-flash` | Flash-class model name |
| `GEMINI_THINKING_LEVEL` | no | `low` | Gemini thinking depth (`low`/`medium`/`high`). Empty omits the field |
| `OPENAI_API_KEY` | for OpenAI | empty | OpenAI key |
| `OPENAI_MODEL` | no | `gpt-4o-mini` | OpenAI model name |
| `AI_TIMEOUT` | no | `120` | Seconds for one model call |
| `JOB_TICK_SECONDS` | no | `30` | How often the queue wakes up |
| `SEND_GAP_SECONDS` | no | `0.05` | Minimum gap between channel posts |
| `ADMIN_POST_MIN_CHARS` | no | `200` | Minimum length of an admin post that can start a quiz |
| `ADMIN_POST_QUIZ_DELAY_SECONDS` | no | `600` | Delay before a quiz is generated from an admin post |
| `POINTS_PER_CORRECT_ANSWER` | no | `10` | Points granted for one correct quiz answer |
| `LEADERBOARD_ANNOUNCE_TIME` | no | `09:00` | Default local time for a new weekly leaderboard schedule |
| `PAYMENT_CARD_NUMBER` | for payments | empty | Receiving card number shown to owners who pay manually |
| `PAYMENT_CARD_HOLDER` | for payments | empty | Name of the card holder shown with the number |
| `PAYMENT_CARD_TYPE` | no | empty | Card network shown on the payment screen, for example Uzcard |
| `PAYMENT_CARD2_NUMBER` | no | empty | Optional second receiving card, for example a Visa |
| `PAYMENT_CARD2_HOLDER` | no | empty | Holder name for the second card; both number and holder are required to show it |
| `PAYMENT_CARD2_TYPE` | no | empty | Network name for the second card, for example Visa |
| `PAYMENT_TERMS_VERSION` | no | `2026-11-v1` | Version of the payment terms (oferta) the owner accepts; stored on every request. Bump it when the terms change |
| `PAYMENT_REVIEW_HOURS` | no | `12` | Review time promised to the owner in the confirmation message |
| `PAYMENT_DRAFT_TTL_HOURS` | no | `24` | An unpaid request (no receipt yet) expires after this many hours; submitted requests never expire on their own |
| `PAYMENT_FAKE_BLOCK_AFTER` | no | `2` | Fake-receipt marks after which the owner is blocked from paying until a super admin unblocks them |
| `FOUNDER_SLOTS` | no | `20` | How many paying owners can lock in the 30% founder price |
| `PERIOD_DISCOUNTS` | no | `3:7,12:15` | Period discounts as `months:percent` pairs (3 months 7%, 12 months 15%) |
| `BACKUP_DIR` | no | `./backups` | Host folder for `pg_dump` files |
| `BACKUP_RETENTION_DAYS` | no | `14` | How many days to keep dump files |
| `BACKUP_ENABLED` | no | `true` | Daily `pg_dump` sent to every `SUPER_ADMIN_IDS` chat as a document |
| `BACKUP_TIME` | no | `04:00` | Asia/Tashkent time after which the daily backup runs (once per day) |
| `BACKUP_MAX_MB` | no | `45` | Larger dumps are not sent; admins get an alert instead |
| `BACKUP_TIMEOUT_SECONDS` | no | `600` | `pg_dump` time limit |
| `ALERT_COOLDOWN_SECONDS` | no | `300` | Minimum gap between Telegram error alerts to super admins |
| `HEALTH_PORT` | no | `8080` | In-container HTTP health port. `0` disables the server |
| `HEALTH_FILE` | no | `/tmp/ritm-health` | Heartbeat file updated after a successful scheduler tick |
| `HEALTH_STALE_SECONDS` | no | `120` | Age after which the heartbeat file is considered stale |
| `WEBAPP_PORT` | no | `8081` | Mini App HTTP port inside the container. `0` disables it. Published to `127.0.0.1` only |
| `WEBAPP_URL` | no | empty | Public HTTPS origin for the Mini App (Cloudflare tunnel or production domain). Menu buttons stay hidden until this is `https://…` |
| `WEBAPP_AUTH_MAX_AGE` | no | `86400` | Max age in seconds for Telegram `initData.auth_date` |
| `WEBAPP_SESSION_TTL` | no | `43200` | Lifetime of the Mini App session token, in seconds |
| `WEBAPP_SESSION_SECRET` | no | empty | Optional session HMAC secret. When empty, one is derived from `BOT_TOKEN` |
| `PENDING_TTL_HOURS` | no | `24` | How long a pending chat invite is kept |
| `SUPPORT_USERNAME` | no | empty | Telegram username for the Mini App support row (Profil › Qo'llab-quvvatlash). Empty hides the row |


A connected chat can turn on a daily post from its card. The tick enqueues it once per local day, the provider writes the text from the profile, and the sender posts it. AI quota comes from the plan row.

On a Pro, Ultra or trial plan the chat card shows 🏆 Reyting. Each correct quiz answer earns points (`POINTS_PER_CORRECT_ANSWER`, default 10). The weekly Top-10 is posted to the chat on the chosen weekday and time in the chat's timezone (default Monday 09:00). The official post covers the previous Monday–Sunday week. "📣 Hozir e'lon qilish" posts the current week's live standings immediately, without freezing that week.

On a Pro, Ultra or trial plan the chat card can also turn on quizzes from admin posts. A long enough original post in a connected channel, or a message from a group administrator, is stored and a quiz job runs after the delay. Channels get a private deep-link quiz; groups get a native poll.

Prices and plan limits live in the `plans` table, including `founder_price_uzs`. Monthly prices are Start 29 000, Pro 39 000 and Ultra 69 000 so'm. The first 20 paying subscribers get a 30% founder price (20 300 / 27 300 / 48 300); from the 21st subscriber the regular price applies. An owner who already has founder status keeps the founder price on later renewals. Period discounts stack on top of that monthly price (multiplicative): 3 months is 7% off, 12 months is 15% off, then the total is rounded to the nearest 100 so'm. Example: Pro founder 27 300 × 12 × 0.85 = 278 460, charged as 278 500 so'm. The payment stores this total; `subscriptions.price_uzs` stays the locked monthly unit, and `subscriptions.paid_amount_uzs` records the discounted total that was charged.

An owner pays from **💳 Tarif va obuna** → **💳 To'lov**: plan → period → accept the terms (oferta) → the bot shows a unique reference (`RITM-XXXX`), an exact amount (plan price plus a 1–99 so'm offset) and the receiving cards in copyable groups of four. After the transfer the owner taps **✅ To'lov qildim**, enters the last 4 digits of the paying card and the transfer time, and sends the receipt (photo, image or PDF; required). Super admins review under **💰 To'lovlar** in the bot or under **🛡️ Admin** in the Mini App; both use the same service and every step is written to the append-only `payment_events` table. See [docs/payments-trust.md](docs/payments-trust.md).

During a trial, the plan screen has **📊 Sinov hisoboti** to send a live report immediately. Scheduled reports also go out on trial day offsets (for a 5-day trial: days 1, 2 and 3; for a 15-day trial: days 3, 8 and 13). One expiry notice is sent when the trial ends.

## Tests and lint

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
ruff check .
ruff format --check .
pytest
```

## Migrations

From the project root, with `DATABASE_URL` exported:

```bash
alembic revision -m "describe the change"
# edit migrations/versions/<revision>.py — implement upgrade() and downgrade()
alembic upgrade head
```

Do not call `Base.metadata.create_all` from the application.

## Layout

Routers call services. Services call repositories. Repositories are the only code that touches SQLAlchemy queries. User-facing text is in `app/locales`.


## Backups

**Daily Telegram backup (Render and Docker):** when Telegram mode is not `off`, the bot runs `pg_dump --format=custom --compress=6` once per Asia/Tashkent day after `BACKUP_TIME`, sends the file to each super admin and deletes the temp file. The day is recorded in `system_state` (`backup_last_day`, result in `backup_last_result`), so restarts do not send it twice. The password reaches `pg_dump` only through `PGPASSWORD`. Restore with `pg_restore --clean --if-exists --no-owner --no-acl -d "<url>" ritm-YYYY-MM-DD.dump`.

The database is dumped with `pg_dump` (custom format) into `BACKUP_DIR` (default `./backups` on the host, not inside the Postgres volume). Old files named `ritm-*.dump` are deleted after `BACKUP_RETENTION_DAYS` (default 14).

On the same Docker Compose stack as the bot (recommended on Windows, and whenever Postgres is not published on the host):

```bash
docker compose -f docker-compose.yml --profile backup run --rm backup
```

The `backup` service is profile-gated, so `docker compose up -d` does not run a dump by itself. Schedule the same command with Task Scheduler (Windows) or cron (Linux), for example daily at 03:00.

To restore onto a running `postgres` service:

```bash
docker compose -f docker-compose.yml cp backups/ritm-YYYYMMDD-HHMMSS.dump postgres:/tmp/restore.dump
docker compose -f docker-compose.yml exec -T postgres pg_restore --clean --if-exists -U bot -d engagement /tmp/restore.dump
```

If you run `scripts/backup_db.sh` on a host that has `pg_dump`, point `DATABASE_URL` at a reachable address (on the user's PC the database port is not published in the base compose file, so prefer the Compose `backup` service).

## Health and monitoring

The bot process listens on `HEALTH_PORT` (default 8080, not published to the host) at `/health`. A successful tick also refreshes `HEALTH_FILE`. Docker healthchecks call `python scripts/healthcheck.py`, which prefers the HTTP probe and falls back to the heartbeat file.

Super admins can open **🩺 Tizim holati** in the admin panel: database latency, age of the last scheduler tick, the configured AI provider/model (not the API key), pending jobs, and failed jobs in the last 24 hours.

Unhandled errors are logged with a traceback and a correlation id (`update_id` or `job_id`). A short alert is also sent to `SUPER_ADMIN_IDS`, at most once every `ALERT_COOLDOWN_SECONDS`. Alerts and logs include only ids and the exception type — never message text, tokens, card numbers or API keys.


Every bot-chat setting can also be changed in the Mini App; see [docs/settings.md](docs/settings.md).

## Telegram Mini App (local test)

The bot process also serves the Mini App on `WEBAPP_PORT` (default `8081`). The Compose file publishes that port only on `127.0.0.1`, so it is not exposed on the LAN. Telegram still needs a public HTTPS URL, so a profile-gated Cloudflare quick tunnel is included.

On Windows (from `C:\Users\Adham\Projects\ritm-ai\engagement-bot`), use the base Compose file only — do not start `docker-compose.override.yml` (port 5432 is already taken):

```powershell
docker compose -f docker-compose.yml up --build -d
docker compose -f docker-compose.yml --profile tunnel up -d
docker compose -f docker-compose.yml logs tunnel
```

In the tunnel logs, copy the `https://....trycloudflare.com` URL (it appears after `Registered tunnel connection`). Put it in `.env` as `WEBAPP_URL` with no trailing slash, then recreate the bot so the menu button picks it up:

```powershell
docker compose -f docker-compose.yml up -d --force-recreate bot
```

Leave the tunnel running while you test. If the tunnel container restarts, Cloudflare issues a **new** URL — update `WEBAPP_URL` and recreate the bot again.

The bot shows **📱 Mini ilova** in the private menu and sets the Telegram chat menu button only when `WEBAPP_URL` starts with `https://`. Later, point `WEBAPP_URL` at your cloud HTTPS domain and drop the tunnel profile.

## Production deploy

### BotFather

1. `/newbot` (or use the existing `@ritm_airobot`).
2. `/setname` → `Ritm AI`.
3. `/setuserpic` → upload the square bot icon.
4. `/setprivacy` → Disable, so the bot can see group messages it needs for quizzes.
5. `/setcommands` → `start`, `menu`, `help`, `cancel` (the process also applies these at startup).
6. After `WEBAPP_URL` is set, the process calls `setChatMenuButton` at startup. You can also use BotFather `/setmenubutton` with the same HTTPS URL.

### Docker on a VPS

1. Copy the project and create `.env` from `.env.example`. Set `BOT_TOKEN`, `GEMINI_API_KEY` (or OpenAI), `SUPER_ADMIN_IDS`, and the receiving card fields.
2. Use only `docker-compose.yml` in production. It does **not** publish Postgres on port 5432. Do not start with `docker-compose.override.yml` (that file maps 5432 for local development and will fail if the host port is already taken).
3. `docker compose -f docker-compose.yml up --build -d`
4. The bot container runs `alembic upgrade head` before polling. Plans are seeded by migrations.
5. Check `docker compose -f docker-compose.yml ps` — `postgres` and `bot` should be healthy — and `/menu` in Telegram. Open **🩺 Tizim holati** as a super admin.

Optional resource limits (uncomment or add under each service if the VPS is small):

```yaml
    deploy:
      resources:
        limits:
          memory: 512M
```

### Render

1. Create a PostgreSQL instance and a Web Service (or a Background Worker) from this repo, Docker runtime.
2. Set `DATABASE_URL` to Render's URL, changing the scheme to `postgresql+asyncpg://`.
3. Set the same env vars as in the table above. Point Render's health check at `http://localhost:8080/health` (the service must listen, but does not need a public website).
4. Long polling works on a single instance. Do not run two pollers with the same `BOT_TOKEN`.
5. Migrations run in `entrypoint.sh` on boot. Add a Render cron job that runs the backup script against the Render database if you want retained dumps (store them on a disk or object storage; the local `./backups` folder is ephemeral on Render).

## If the bot goes down

1. `docker compose -f docker-compose.yml ps` and `docker compose -f docker-compose.yml logs bot --tail=200`. Look for a recent `job tick failed` or `update failed` line (ids only).
2. Confirm the healthcheck: `docker compose -f docker-compose.yml exec bot python scripts/healthcheck.py` or open **🩺 Tizim holati**.
3. If the database is the problem, restore the latest `backups/ritm-*.dump` with the steps above.
4. Restart order: `docker compose -f docker-compose.yml up -d postgres`, wait until it is healthy, then `docker compose -f docker-compose.yml up -d bot`.
5. If Telegram 409 "terminated by other getUpdates" appears, another process is already polling — stop the duplicate.
