# Settings: bot chat ⇄ Mini App

Every setting an owner can change in the bot chat can also be changed in the Mini App.
Both sides call the same services, so validation and permissions are identical.

## Where each setting lives

| Setting | Bot | Mini App | Service | Who may change it |
|---|---|---|---|---|
| UI language (uz/ru/en) | `/start` picker (first visit), `/language`, menu **🌐 Til** | Profil › Ilova tili | `user_prefs.set_language` / `update_prefs` | the user |
| Chat profile: niche (preset or custom ≤200), description ≤500, tone, audience, content language, time zone | Chat card › Profilni tahrirlash (wizard) | Chat › ✏️ Profilni tahrirlash (`#/chats/edit/<id>`) | `ProfileService.save` (`validate_profile`) | owner; admins only when `admins_can_edit` |
| Daily post time / on-off | Chat card › Kunlik post | Chat › Kunlik post | `OwnerPanel.update` | owner; admins with `admins_can_edit` |
| Quiz time / on-off | Chat card › Quiz | Chat › Quiz | same | same |
| Leaderboard weekday, time, on-off | Chat card › Reyting | Chat › Reyting | same | same |
| Post-quiz on/off | Chat card | Chat › Quiz | same | same |
| Admins may edit | — | Chat › Adminlar | same | owner only |
| Post now / Quiz now / Announce leaderboard now | Chat card | Chat › Tezkor amallar | `enqueue_now` | owner, admins (act) |
| Disconnect chat | Chat card › Uzish | Chat › Chatni uzish | `ChatLifecycleService.disconnect` | owner (and super admin) |
| Connect a chat | add bot → confirm in private chat | Profil › Chat ulash (deeplinks + pending list) | `link_chat` → `ChatLifecycleService.connect` | the Telegram user who added the bot, if still a chat admin |

Mini App only (no bot equivalent needed):

| Setting | Mini App | Notes |
|---|---|---|
| Trial report messages on/off | Profil › Bildirishnomalar | `users.notify_reports`; the notice is still recorded so it is not retried |
| Trial-ending message on/off | Profil › Bildirishnomalar | `users.notify_expiry`; the trial still expires on time |
| Default time zone for new chats | Profil › Vaqt mintaqasi | `users.default_timezone`; pre-selected in the bot wizard and the Mini App form |

Always sent (cannot be turned off): payment results, "bot was removed from a chat" alerts, super-admin payment alerts.

Stays in the bot: the payment flow (receipt upload) and the trial live report.

## HTTP endpoints

| Method | Path | Notes |
|---|---|---|
| GET / PUT | `/api/chats/{id}/profile` | view needs chat access; save needs edit rights. 400 `input_empty` / `input_long` / `input_choice` / `bad_request` |
| POST | `/api/chats/{id}/disconnect` | 403 `owner_only` for admins |
| POST | `/api/chats/{id}/board-now` | `{result: queued|empty|profile|quota…}` |
| GET / PATCH | `/api/me/settings` | language, default time zone, notify flags, support handle |
| GET | `/api/me/payments` | the caller's own payments: RITM code, status, rejection reason |
| GET / POST | `/api/connect` | deeplinks + the caller's pending chats / confirm one |
| POST | `/api/connect/decline` | drop the caller's own pending chat |
| GET | `/api/docs/terms` | the payment terms text and version |

Pending chats are kept in memory by the bot process; they are lost on restart (add the bot again).

## Migration

`0012_user_prefs` adds `users.ui_language_set`, `notify_reports`, `notify_expiry`, `default_timezone`.
Existing users are marked as having chosen a language, so only new users see the `/start` picker.
