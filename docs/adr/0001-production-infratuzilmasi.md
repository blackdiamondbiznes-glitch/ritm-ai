# ADR 0001: Production infratuzilmasi

- Holat: qabul qilindi
- Sana: 2026-11-24
- Tasdiq manbasi: loyiha egasining production muhiti haqidagi tasdig‘i

## Kontekst

Repozitoriydagi eski `render.yaml` Render Postgres va `TELEGRAM_MODE=off`ni ko‘rsatgan. Bu production’ning amaldagi sozlamasiga mos emas. Maxfiy `DATABASE_URL` qiymatini hujjat yoki repoga yozish mumkin emas.

## Qaror

- Ilova Render’dagi Docker web service’da ishlaydi: Free reja, Frankfurt hududi, bitta instansiya.
- Production ma’lumotlar bazasi Neon Postgres. `DATABASE_URL` qiymati Render boshqaruv panelida saqlanadi va Neon’ga ulanadi.
- Production’da `TELEGRAM_MODE=webhook`. Ilova ishlayotgan paytda scheduler ham yoqiladi.
- `render.yaml` web service’ni tavsiflaydi, Render Postgres yaratmaydi. `DATABASE_URL` Render panelida alohida sozlanadi.
- Maxfiy qiymatlar repoga, hujjatga yoki logga kiritilmaydi.

## Oqibatlar

- Render Free xizmati uxlaganda ilova jarayoni va scheduler to‘xtaydi. Webhook so‘rovi xizmatni uyg‘otishi mumkin, ammo scheduler ishlarining uzluksiz bajarilishini kafolatlamaydi.
- Uxlab qolish vaqtida rejalashtirilgan ishlar kechikishi mumkin. Uzluksiz scheduler talab qilinsa, hosting rejasini yangilash yoki scheduler’ni alohida ishchi jarayonga ajratish keyingi qaror bo‘ladi.
- `entrypoint.sh` har ishga tushganda `alembic upgrade head` bajaradi. Faza 1 CI’sida bo‘sh PostgreSQL bazasida migratsiya alohida tekshiriladi.
- `render.yaml` endi Render Postgres’ni ilova bazasi sifatida e’lon qilmaydi. Render boshqaruv panelida qolgan eski resursni ishlatish yoki o‘chirish alohida qaror.
