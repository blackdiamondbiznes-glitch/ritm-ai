# Faza 0 — Kod auditi

**Sana:** 2026-11-24
**Audit qilingan commit:** `32aa866`
**TZ manbasi:** repoda `docs/TZ.md` bor; topshiriqda ko‘rsatilgan `docs/Ritm-AI-TZ.md` yo‘q. `docs/TZ.md` avval berilgan `Ritm-AI-TZ.md` nusxasiga aynan teng.

Audit doirasi: migratsiyalar, HTTP marshrutlari va ekranlar, o‘qituvchi imkoniyatlarining bot/Mini App/veb-panel pariteti, tenant izolyatsiyasi, jarayon ichidagi holat, deploy va panelga kirish. Xulosalar audit qilingan kod holatiga tegishli; ishlab chiqarish muhiti dashboardini repodan aniqlab bo‘lmaydi.

## Qisqa xulosa

- 35 ta Alembic revision statik tahlil qilindi: `0035_panel_login_tokens` yagona head, uning parent’i `0034_meeting_url`. `alembic heads` bu muhitda bajarilmadi, chunki `alembic` CLI o‘rnatilmagan.
- 52 ta `/api/tutor/*` route 14 modulda ro‘yxatdan o‘tgan. Tekshirilgan tutor HTTP handlerlari `_context()` orqali autentifikatsiya qiladi va `ctx.user.id`/`ctx.user`ni servislarga uzatadi; asosiy repository so‘rovlari `owner_id` bilan filtrlanadi. Faza 1 test matritsasi 52 route’ning barchasini boshqa egaga tegishli ma’lumot bilan tekshiradi.
- Tenant himoyasi barcha route’larni qamrab olgan yagona guard emas; servisdagi owner-scope tekshiruvlari to‘g‘ri bajarilishiga bog‘liq. 52 ta route uchun alohida HTTP test matritsasi qo‘shildi.
- Mini App’da o‘qituvchi imkoniyatlari paneldagidan to‘liqroq. Panelda guruhni chatga ulash bor, ammo guruh/o‘quvchini o‘chirish, mavzu/vazifani boshqarish, yakka dars yaratish va qo‘lda eslatma rejalash UI’i yo‘q.
- Yangi mahsulot qaroriga zid ravishda, o‘qituvchi uchun joriy default UI Mini App’dagi `cabinet`; panelga `/panel` orqali alohida kiriladi.
- Ayrim holatlar process-local saqlanadi. `TELEGRAM_MODE=off` bo‘lsa, bot update’lari va rejalashtirilgan ishlar ishlamaydi. `render.yaml` Render Postgres/free plan’ni e’lon qilgan, TZ esa production’da Neon deb yozgan; haqiqiy muhitni egasi tasdiqlashi kerak.

## 1. TZ va kodning joriy holati

| Mavzu | Kodda tekshirilgani | TZ bilan farqi / oqibati |
|---|---|---|
| Kod snapshot’i | Audit qilingan `HEAD` — `32aa866`; TZ boshida `afa8f9f` deb ko‘rsatilgan. | TZdagi kod snapshot’i eskirgan. |
| Migratsiyalar | `migrations/versions/` ichida 35 revision bor; AST orqali parent bog‘lanishlari uzilmagani va yagona head `0035_panel_login_tokens` ekani tekshirildi. | `alembic heads` CLI ishlamadi; natija migration metadata’ni statik o‘qishga asoslangan. CI’da dinamik tekshiruv yo‘q. |
| Marshrut va ekranlar | `app/webapp/server.py` Mini App API va `/panel` marshrutlarini ro‘yxatdan o‘tkazadi. Tutor API group, student, session/lesson, attendance, fee, reminder, grade/homework, report va export modullariga bo‘lingan. | API marshruti mavjudligi shu amal panel UI’da ham bor degani emas; quyidagi jadvalda UI alohida tekshirildi. |
| Tutor guruhini chatga ulash | `NotifyService.link_chat()` egasining faol community chat’ini tutor guruhiga bog‘laydi. Mini App va paneldagi guruh ekrani shu API’ni ishlatadi. | TZ 3.2 dagi “panelda yo‘q” degan belgi eskirgan. Yangi community chat’ni paneldan platformaga ulash esa boshqa oqim bo‘lib, panelda yo‘q. |
| Panel bosh sahifasi | `PanelHome.for_owner()` bugungi darslar, belgilanmagan davomat, muddati o‘tgan to‘lovlar, so‘rovlar va tushumni chiqaradi; `homework` hozir `None`. | Vazifani topshirish va baholash panelda amalga oshmagan; bosh sahifadagi vazifalar navbati hozircha ishlamaydi. |
| O‘qituvchining asosiy yuzasi | `vertical.js` o‘qituvchi uchun `cabinet` tabini beradi; `app.js` o‘qituvchini sukut bo‘yicha `cabinet`ga yo‘naltiradi. Panelga bot yuborgan bir martalik havola orqali kiriladi. | “O‘qituvchining asosiy yuzasi = panel” qarori joriy yo‘naltirishda aks etmagan. Mini App’ni o‘chirish shart emas; keyingi bosqichda panelga kirish va CTA ustuvorligini o‘zgartirish kerak. |

## 2. O‘qituvchi imkoniyatlari: bot / Mini App / panel

**Bor** — asosiy amallar shu yuzada bajariladi; **Qisman** — faqat ko‘rish/qabul qilish yoki ayrim amallar mavjud; **Yo‘q** — tegishli UI amali yo‘q. Botdagi “ko‘rish” avtomatik xabar/karta olishni anglatadi, to‘liq boshqaruvni emas.

| Imkoniyat | Telegram bot | Mini App | `/panel` |
|---|---|---|---|
| Guruh CRUD | Qisman — qo‘shilish havolasi/so‘rovi; guruh yaratish, tahrirlash, o‘chirish UI’i yo‘q | Bor — yaratish, tahrirlash, o‘chirish, o‘quvchini bog‘lash/ajratish | Qisman — yaratish/tahrirlash va o‘quvchini bog‘lash/ajratish bor; guruhni o‘chirish UI’i yo‘q |
| O‘quvchi CRUD | Qisman — qo‘shilish so‘rovini tasdiqlash/rad etish; o‘quvchi kartasining to‘liq CRUD’i yo‘q | Bor — karta, tahrirlash/o‘chirish, guruhga bog‘lash | Qisman — ro‘yxat, yaratish/tahrirlash bor; o‘quvchini to‘liq o‘chirish UI’i yo‘q |
| Mavzu va vazifa matni | Qisman — o‘quvchi vazifa/xabarnomani ko‘radi; o‘qituvchi botda yaratmaydi/tahrirlamaydi | Bor — mavzu, baho va vazifa matni/muddati | Yo‘q — panelda topic/homework moduli yoki UI yo‘q |
| Vazifani topshirish/baholash | Yo‘q — F bosqichidagi topshirish va baholash kodda yo‘q | Yo‘q — hozircha vazifani ko‘rish mumkin, topshirish/baholash yo‘q | Yo‘q — `PanelHome.homework` `None` |
| Yakka dars | Qisman — dars xabari/kartasini olishi mumkin; yaratish/tahrirlash UI’i yo‘q | Bor — `/api/tutor/lessons` CRUD | Yo‘q — panel yangi dars qo‘shishda `/api/tutor/groups/{id}/sessions`dan foydalanib guruh tanlatadi; yakka `lessons` UI’i yo‘q |
| Tutor guruhini Telegram chat’ga ulash | Yo‘q — botdagi `connect` community chat’ni platformaga ulash uchun, tutor guruhini bog‘lash uchun emas | Bor — guruh xabarnomasi/chat sozlamalari | Bor — guruh sahifasidagi chat tanlovi `/api/tutor/groups/{id}/chat`ni ishlatadi |
| Davomat | Bor — widget yoqilganida bot kartasidan belgilash mumkin | Bor — davomat sahifasi va oylik ko‘rinish | Bor — bosh sahifa, jadval va davomat sahifasi |
| Kurs to‘lovi | Qisman — o‘quvchi to‘lov kartasi/xabarnomasini olishi mumkin; o‘qituvchi botda to‘lov qayd qilmaydi | Qisman — hisoblar ro‘yxati va to‘lov qayd etish bor; qoida sozlash, to‘lovni bekor qilish va qarzni kechirish UI’i yo‘q | Bor — qoida, to‘lov qayd etish va qarzni kechirish |
| Eslatmalar | Qisman — bot avtomatik yuboradi/qabul qiladi; o‘qituvchining barcha eslatmalarini boshqarish UI’i emas | Bor — guruh qoidalari va qo‘lda rejalashtirilgan eslatmalar | Qisman — guruh darsi/to‘lovi uchun avtomatik eslatma sozlamalari bor; `/api/tutor/reminders` UI’i yo‘q |
| Hisobot | Bor — Pro/Ultra’da oylik tutor hisoboti botga yuboriladi | Bor — oylik hisobot sahifasi | Bor — oylik hisobot va bosh sahifa |
| CSV eksport | Yo‘q | Bor — o‘quvchi/to‘lov/davomat CSV | Bor — o‘quvchi/to‘lov/davomat CSV |

Tekshirilgan asosiy manbalar: `app/webapp/static/vertical.js`, `app.js`, `panel.js`, `panel_people.js`, `panel_schedule.js`, `panel_money.js`; API’da `group_routes.py`, `student_routes.py`, `lesson_routes.py`, `session_routes.py`, `grade_routes.py`, `notify_routes.py`, `fee_routes.py`, `reminder_routes.py`, `report_routes.py`, `export_routes.py`; botda `routers/enroll.py`, `routers/study.py`, `routers/widget_queries.py`, `jobs/tutor_report.py`.

## 3. Tenant izolyatsiyasi

### Tekshiruvda tasdiqlangan

- Tutor HTTP handlerlari `_context()` orqali imzolangan session’ni tekshiradi va Telegram foydalanuvchisini bazadan qayta topadi. Bloklangan foydalanuvchi rad etiladi.
- Guruh, o‘quvchi, dars, sessiya, davomat, to‘lov, eslatma, hisobot va eksport handlerlari `ctx.user.id`ni owner parametri sifatida servisga uzatadi. Masalan, group/student servislar `get_owned()` ishlatadi; invoice/payment so‘rovlari guruhning `owner_id`ini tekshiradi.
- Tutor guruhiga ulanadigan community chat `NotifyService._chat()` orqali aynan shu egasiga tegishli va faol ekani qayta tekshiriladi.
- Ko‘rilgan `/api/tutor/*` yo‘llarida tasdiqlangan tenant ma’lumotlari sizishi topilmadi. Ko‘p ID-amallari boshqa egaga tegishli yozuvni topilmagandek `404` bilan qaytaradi.

### Qolgan xavf va test bo‘shliqlari

- Tenant himoyasi har bir obyektni avtomatik filtrlaydigan umumiy HTTP middleware emas; owner ID’ni to‘g‘ri uzatish va servis ichida tekshirishga tayanadi. Yangi endpoint yoki servis tekshiruvni unutsa, xavf tug‘iladi.
- Repository’larda owner’siz `get(id)` kabi yordamchi metodlar bor; ayrimlari bot/o‘quvchi oqimlari uchun mo‘ljallangan. Tutor HTTP oqimida ulardan faqat owner tekshiruvidan keyin foydalanish kerak.
- `tests/test_tutor_tenant_matrix_http.py` ro‘yxatdan o‘tgan route-method juftliklarini test ro‘yxati bilan solishtirib, 52 route’ning har birini boshqa egasining ma’lumoti bilan tekshiradi. Obyekt ID’sidan foydalanadigan amallar 404 qaytaradi, ro‘yxatlar esa begona yozuvlarni chiqarmaydi.
- Noto‘g‘ri yoki boshqa egaga tegishli bog‘lovchi ID’lar tegishli tutor API’larida 404 bilan qaytariladi; bu xatti-harakat uchun guruh, o‘quvchi, dars va eslatma handlerlarining xato xaritasi yangilandi.

## 4. Jarayon ichidagi holat va ko‘p instance

| Holat | Qayerda saqlanadi | Restart/ko‘p instance ta’siri |
|---|---|---|
| aiogram FSM | `Dispatcher(storage=MemoryStorage())` | Restartda foydalanuvchi oqimining bosqichi/ma’lumoti yo‘qoladi; update boshqa instance’ga tushsa u FSM holatini topmaydi. |
| Tasdiqlanmagan community chat | `PendingChatStore` ichidagi dict, `pending_ttl_hours` bilan | Restartda kutayotgan chat yo‘qoladi; instance’lar ro‘yxati farq qilgani uchun boshqa instance’da tasdiqlash ishlamasligi mumkin. |
| API/pay rate limiter | `RateLimiter` va process-local limiter’lar | Har bir instance limitni alohida hisoblaydi; replica ko‘payganda umumiy ruxsat etilgan so‘rovlar ham ko‘payadi. Restart counter’larni tozalaydi. |
| Telegram admin/member keshi, bot yuborish tezligi | Process-local dict/obyektlar | Replica’larda kesh va yuborish holati farq qiladi; bu ko‘proq izchillik va Telegram API yuklamasiga ta’sir qiladi. |
| Mini App Bearer session | Serverda saqlanmaydi; HMAC imzoli, `exp` muddati bor token. Brauzer tokenni runtime xotirasida saqlaydi, `localStorage`ga esa faqat dashboard nusxasini yozadi. | Barcha instance’da signing secret/sozlamalar bir xil bo‘lsa token tekshiriladi. Tokenni serverdan darhol bekor qilib bo‘lmaydi; secret almashtirilsa barcha session’lar yaroqsiz bo‘ladi. |
| Panel cookie session | Mini App bilan bir xil stateless signed token; cookie 12 soat amal qiladi | Serverda session revoke yo‘q; logout faqat joriy brauzer cookie’sini o‘chiradi. |
| Background tick/job queue | APScheduler process-local; job PostgreSQL’da, claim `FOR UPDATE SKIP LOCKED` bilan | Job claim’lari takroriy ishlashdan himoyalangan. Ammo bir nechta scheduler tick oldi tayyorgarligi/refill ishlarini takrorlamasligini audit tasdiqlamadi. |

## 5. Deploy va CI xavflari

- `.github/workflows/` yo‘q va Git’da GitHub Actions workflow topilmadi. Shuning uchun push/PR’da Ruff, pytest, migration upgrade/head tekshiradigan avtomatik gate yo‘q.
- Konteyner har ishga tushganda `entrypoint.sh` `alembic upgrade head` bajaradi. Xato bo‘lsa 2 soniya oralatib 30 martagacha takrorlaydi; bajarilmasa app ishga tushmaydi. Bu vaqtinchalik DB uzilishini yengadi, ammo production migration deploy startup’iga bog‘langan va CI’da oldindan tekshirilmaydi.
- `render.yaml` Render Postgres, free web service va `TELEGRAM_MODE=off`ni belgilaydi. Izohga ko‘ra `off` holatida Telegram update’lari va scheduled job’lar ishlamaydi. Manifest izohida free DB 30 kundan keyin tugashi ham qayd etilgan.
- `docs/render.md` Render Postgres’ni ishlatilayotgan muhit sifatida tasvirlaydi; `docs/TZ.md` esa production’da Neon deb ko‘rsatib, ziddiyatni ochiq qoldirgan. Haqiqiy production DB va Render dashboard’dagi `TELEGRAM_MODE`ni repo orqali tasdiqlab bo‘lmaydi. Manifest production’da aynan ishlatilsa, bot, eslatma, to‘lov, sessiya va hisobot ishlari yurmaydi.
- Xulosa: production DB va Telegram mode’ning haqiqiy qiymatini 1-faza ADR 0001 uchun egasidan tasdiqlatish; migration’larni deploy’dan oldin CI’da tekshirish.

## 6. Panel login va qayta kirish

- `/panel` havolasi bot’dagi `/panel` buyrug‘i yoki Mini App orqali yuboriladi. Magic link bir marta ishlaydi va 15 daqiqa amal qiladi; bazada faqat xeshi saqlanadi.
- `ritm_panel` cookie `HttpOnly`, `Secure`, `SameSite=Lax`; muddati `webapp_session_ttl` bilan bir xil, sukut bo‘yicha **43 200 soniya (12 soat)**.
- “Meni eslab qolish” tanlovi va Telegram Login Widget zaxira kirishi kodda yo‘q. 12 soatdan keyin o‘qituvchi botga `/panel` yuborib yangi havola oladi. Ayrim ichki brauzerlarda muammo bo‘lsa, Chrome’da ochish ko‘rsatmasi bor.
- Session stateless: chiqish brauzerdagi cookie’ni o‘chiradi, ammo avval nusxalangan cookie/tokenni serverdan bekor qilmaydi; token muddati tugaguncha yoki signing secret almashguncha amal qiladi.

## 7. Faza 0 natijasi va keyingi qadamlar

Faza 0 doirasida kod o‘zgartirilmadi. Keyingi fazani boshlashdan oldin:

1. Production DB Neonmi yoki Render Postgresmi va haqiqiy production `TELEGRAM_MODE` qandayligini tasdiqlash.
2. O‘qituvchining default yo‘naltirishi/CTA’sini panelni asosiy yuza qiladigan tarzda rejalash; Mini App kabinetini zaxira yuza sifatida qoldirish.
3. 1-fazada CI, PR/issue shablonlari, ADR’lar, cross-owner testlarning to‘liq matritsasi va backup tiklash yo‘riqnomasini alohida PR’da bajarish.
