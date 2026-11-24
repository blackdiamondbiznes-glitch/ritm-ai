# Ritm AI’ni Render’da ishga tushirish

## Production muhiti

Tasdiqlangan production sozlamalari:

- Render’da `ritm-ai` nomli Docker web service, Frankfurt hududi, Free reja va bitta instansiya.
- Ma’lumotlar bazasi Neon Postgres. `DATABASE_URL` maxfiy qiymati Render boshqaruv panelida saqlanadi va Neon’ga ulanadi.
- `TELEGRAM_MODE=webhook`; webhook, Mini App va sog‘liq tekshiruvi bitta web service’da ishlaydi.
- `TELEGRAM_MODE` `off` bo‘lmaganda APScheduler yoqiladi. Render Free xizmati uxlaganda ilova jarayoni ham, scheduler ham ishlamaydi. Webhook so‘rovi xizmatni uyg‘otishi mumkin, ammo bu jadval ishlarining uzluksiz bajarilishini kafolatlamaydi.

`render.yaml` faqat web service’ni tavsiflaydi. U Render Postgres yaratmaydi. Blueprint orqali yangi muhit yaratilganda `DATABASE_URL` qiymatini boshqaruv panelida Neon ulanish manzili bilan sozlash kerak. Maxfiy qiymatlarni repoga yozmang.

## Muhim muhit o‘zgaruvchilari

| O‘zgaruvchi | Qiymat yoki manba | Izoh |
|---|---|---|
| `TELEGRAM_MODE` | `webhook` | Telegram yangilanishlari webhook orqali olinadi; scheduler ham yoqiladi |
| `DATABASE_URL` | Render panelidagi maxfiy qiymat | Neon Postgres’ga ulanadi; `postgres://` manzili `postgresql+asyncpg://` ko‘rinishiga moslashtiriladi |
| `HEALTH_PORT` | `0` | Sog‘liq tekshiruvi Render bergan `$PORT` orqali `/health` manzilida ishlaydi |
| `PORT`, `RENDER_EXTERNAL_URL` | Render tomonidan beriladi | Web service porti va odatiy ochiq manzil |
| `WEBAPP_URL` | Ixtiyoriy | Berilmasa `RENDER_EXTERNAL_URL` ishlatiladi |
| `WEBHOOK_SECRET` | Ixtiyoriy maxfiy qiymat | Webhook yo‘li va `X-Telegram-Bot-Api-Secret-Token` uchun; bo‘sh bo‘lsa `BOT_TOKEN`dan hosil qilinadi |
| `BOT_TOKEN` va boshqa kalitlar | Render panelida | Qiymatlarni repoga yoki loglarga kiritmang |

## Ishga tushirish va tekshirish

`entrypoint.sh` ilova ishga tushishidan oldin `alembic upgrade head` buyrug‘ini bajaradi; baza vaqtincha ulanmasa, 2 soniya oralatib 30 martagacha takrorlaydi. So‘ng `python -m app.main` ishga tushadi. PR tekshiruvlarida bo‘sh PostgreSQL’da migratsiya muvaffaqiyatli bajarilishi shart.

Yangi deploy’dan keyin:

1. `/health` manzilining javobini tekshiring.
2. `DATABASE_URL` Render panelida Neon’ga yo‘naltirilganini tekshiring; to‘liq ulanish manzilini ulashmang.
3. Telegram webhook holatini tekshirib, `/start` va Mini App’ni sinang.
4. Free rejada xizmat uxlaganda yoki qayta ishga tushganda scheduler vaqtincha to‘xtashini hisobga oling. Scheduler uzluksiz ishlashi zarur bo‘lsa, Render rejasini yangilashni alohida hal qiling.

Webhook rejimida ayni bot token bilan polling ishlatmang: polling boshlanganda webhook o‘chirilishi mumkin. `TELEGRAM_MODE=off` faqat Mini App va sog‘liq tekshiruvini qoldirib, Telegram yangilanishlari hamda scheduler’ni to‘xtatadi.

Joriy zaxira nusxasi oqimi PostgreSQL dump’ini Telegram orqali adminga yuboradi. Bu maxfiylik, saqlash va tiklash ishonchliligi uchun xavf tug‘diradi; shifrlangan alohida saqlashga o‘tish taklif qilinadi, ammo bu o‘zgarishda amalga oshirilmaydi.
