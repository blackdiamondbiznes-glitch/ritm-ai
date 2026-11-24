# Faza 2 — Veb-panel rejasi

- Holat: bajarishdan oldingi taklif
- Chegara: bu hujjat reja; dizayn, kod, API yoki migratsiya o‘zgartirilmaydi.

## Maqsad va qoidalar

O‘qituvchi uchun asosiy ish joyi `/panel`, Mini App kabineti esa telefondagi zaxira
yuzasi bo‘lib qoladi. Faza 2 dagi barcha amallar mavjud tutor API’laridan foydalanadi,
agar yangi endpoint zarur bo‘lsa u alohida asoslanadi. Har bir so‘rov egasining
ma’lumotlari bilan cheklanadi; matnlar o‘zbek, rus va ingliz tillarida bo‘ladi.

Auditdagi panel bo‘shliqlari: guruh va o‘quvchini o‘chirish, mavzu va uy vazifasini
boshqarish, yakka dars yaratish, qo‘lda eslatma rejalash. Hozirgi API bu amallarning
ko‘pini bajaradi; panel UI’i yetishmaydi.

## A. Paneldagi amallar pariteti

| Amal | Mavjud API | Kerakli UI | Sinov rejasi |
|---|---|---|---|
| Guruhni o‘chirish | `DELETE /api/tutor/groups/{group_id}` | Guruh sahifasida aniq nomi ko‘rsatilgan tasdiq oynasi; bekor qilish va muvaffaqiyatdan so‘ng guruhlar ro‘yxatiga qaytish. Bog‘liq dars, davomat va hisob oqibatlarini oynada tushuntirish. | `tests/test_panel.py` orqali o‘chirish va egaga tegishlilik; tasdiq/bekor qilish, muvaffaqiyatli qaytish va xato xabari uchun UI sinovi. |
| O‘quvchini o‘chirish | `DELETE /api/tutor/students/{student_id}` | O‘quvchi kartasida ism bilan tasdiq; bekor qilishda API chaqirilmasin; o‘chirgach ro‘yxatga qaytish. | API o‘chirish va boshqa egaga tegishli ID uchun 404; tasdiqlash/bekor qilish UI oqimi; guruh a’zoligi va bog‘liq yozuvlar xatti-harakati. |
| Mavzu va uy vazifasi | `POST /api/tutor/groups/{group_id}/topics`, `GET/PUT /api/tutor/groups/{group_id}/topics/{topic_id}`, `PUT /api/tutor/groups/{group_id}/topics/{topic_id}/homework` | Guruh ichida mavzular ro‘yxati, mavzu yaratish/tahrirlash, vazifa matni va muddati; bo‘sh holat, saqlash/yuklanish va xato holatlari. | API tekshiruvi, saqlash va qayta o‘qish, boshqa egaga tegishli guruh yoki mavzu uchun 404; panelda yaratish, tahrirlash va bo‘sh holat. |
| Yakka dars yaratish | `GET/POST /api/tutor/lessons`; tahrirlash/o‘chirish uchun `PATCH/DELETE /api/tutor/lessons/{lesson_id}` | Jadvaldagi “Dars qo‘shish” oqimida guruh tanlashni majburiy qilmaslik; o‘quvchi ixtiyoriy, mavzu, sana/vaqt, muddat va onlayn havola maydonlari. Guruh darsi oqimi o‘z holicha qoladi. | API’da guruhsiz dars yaratish, sana/vaqt va o‘quvchi tekshiruvi, egalararo 404; panelda yangi dars jadvalda paydo bo‘lishi va tahrirlanishi. |
| Qo‘lda eslatma | `GET/POST /api/tutor/reminders`, `DELETE /api/tutor/reminders/{reminder_id}` | Sozlamalar yoki alohida “Eslatmalar” bo‘limida ro‘yxat, yangi eslatma shakli, ixtiyoriy o‘quvchi, vaqt va matn; o‘chirish tasdig‘i, yuborilgan/kutilayotgan holat. | API’da yaratish, ro‘yxat, o‘chirish, vaqt/matn tekshiruvi va egalararo 404; panelda yozuv ro‘yxatga tushishi va o‘chirilishi. |

`tests/test_tutor_tenant_matrix_http.py` dagi egalararo matritsa saqlanadi. Panel UI
sinovlari API’ni to‘liq o‘rnini bosmaydi: UI’dan tashqari route-method egalararo
tekshiruvlari ham qoladi. Mavjud avtomatlashtirish asosan Python API va statik
tekshiruvlardan iborat; amaliy UI tasdiqlashida klaviatura va planshet o‘lchamlari uchun
brauzer sinovi yoki aniq qo‘lda qabul ro‘yxati ishlatiladi.

Hozir loyihada to‘liq brauzer sinovlari uchun maxsus to‘plam yo‘q. UI amallarini
avtomatik tekshirish uchun birinchi PR’da Playwright asosidagi kichik sinov to‘plami va CI ishini
qo‘shish taklif qilinadi. Ungacha har bir UI vazifasi uchun qo‘lda qabul ro‘yxati
saqlanadi; API egalararo va migratsiya sinovlari avtomatik qoladi.

## B. Panelga kirish va sessiyalar

### Tavsiya etiladigan tuzilma

Hozir `panel_login_tokens` bir martalik havolani xesh ko‘rinishida saqlaydi va 15 daqiqada
bekor bo‘ladi. Havola orqali yaratiladigan `ritm_panel` cookie esa imzolangan, holatsiz
token; standart amal muddati 12 soat. Chiqish cookie’ni o‘chiradi, serverdagi tokenni
bekor qilmaydi.

Yangi `panel_sessions` jadvali taklif qilinadi:

| Ustun | Maqsad |
|---|---|
| `id` | Sessiyaning ichki identifikatori |
| `user_id` | Sessiya egasi, `users.id` ga tashqi kalit |
| `token_hash` | Tasodifiy bearer qiymatining SHA-256 xeshi; yagona va maxfiy qiymat saqlanmaydi |
| `device_label` | O‘qituvchiga ko‘rsatiladigan qisqa qurilma belgisi; foydalanuvchi agentidan olingan ma’lumot ishonchli identifikator deb olinmaydi |
| `created_at`, `last_active_at` | Yaratilgan va oxirgi faollik vaqti |
| `expires_at`, `absolute_expires_at` | Harakatsizlik muddati va eng uzoq amal muddati |
| `remember_me` | Uzoq muddatli sessiya tanlanganini bildiradi |
| `revoked_at` | Bekor qilingan vaqt; qiymat bo‘lsa sessiya rad etiladi |

Cookie tasodifiy, taxmin qilib bo‘lmaydigan tokenni olib yuradi. Har bir so‘rovda token
xeshi topilib, foydalanuvchi, `expires_at` va `revoked_at` tekshiriladi. Token xeshi
topilmasa yoki baza tekshiruvi bajarilmasa, kirish rad etiladi; sessiya holati xatosi
muvaffaqiyat shaklida yashirilmaydi. `last_active_at` yozuvi har so‘rovda emas, masalan,
kamida besh daqiqalik oraliqda yangilanadi. Muddati tugagan va bekor qilingan qatorlar
cheklangan davrda tozalanadi.

“Meni eslab qol” uchun taklif qilinadigan qiymatlar: oddiy sessiya — hozirgi 12 soat;
eslab qolingan sessiya — 30 kunlik harakatsizlik muddati va 90 kunlik mutlaq chegara.
Bu muddatlar taklif, yakuniy qiymat kod yozishdan oldin tasdiqlanadi. Panel sozlamalarida
faol qurilmalar, oxirgi faollik va joriy sessiya belgisi ko‘rsatiladi; joriy sessiyani
bekor qilish va barcha qurilmalardan chiqish amallari beriladi.

### Kirish yo‘llari va migratsiya

1. Alembic migratsiyasi faqat `panel_sessions` jadvali va kerakli indekslarni qo‘shadi.
   `panel_login_tokens`, mavjud cookie nomi yoki boshqa ma’lumotlar o‘chirilmaydi.
2. Bir martalik havola oqimi saqlanadi: havola ishlatilgach yangi server sessiyasi
   yaratiladi. Cookie atributlari `HttpOnly`, `Secure`, `SameSite=Lax` va `Path=/` bo‘lib
   qoladi.
3. O‘tish davrida mavjud stateless cookie’lar eng ko‘pi bilan amaldagi 12 soat tugaguncha
   qabul qilinadi. Ularni serverdan bekor qilib bo‘lmaydi; bu cheklov o‘tish davrida ham
   qoladi. Yangi sessiyalar bekor qilinadigan bo‘ladi. Eski tokenlarni qabul qilish
   muddatini tugatish keyingi, alohida PR’da bajariladi.
   Yangi, tasodifiy sessiya cookie’sini chiqarish faqat uni taniydigan kod barcha
   ilova nusxalariga tarqalgach yoqiladi. Avvalgi tokenni o‘qish qo‘llab-quvvatlanadi;
   orqaga qaytarish kerak bo‘lsa yangi cookie o‘chiriladi va qayta kirish talab qilinadi.
   Jadval va avvalgi token ma’lumotlari saqlanadi.
4. CSRF va `Origin` tekshiruvlari logout, joriy sessiyani bekor qilish va barcha
   sessiyalarni bekor qilish POST amallarida saqlanadi. “Barcha qurilmalardan chiqish”
   faqat shu foydalanuvchining faol sessiyalarini bekor qiladi.
5. Telegram Login Widget zaxira yo‘li bo‘ladi. Widget uchun BotFather’da
   `/setdomain` orqali production’dagi aniq domen ro‘yxatdan o‘tkaziladi; domen
   o‘zgarsa, BotFather sozlamasi ham yangilanadi. Server Telegram imzolagan
   ma’lumotni bot tokeni asosida tekshiradi, `auth_date` ning yangiligini nazorat qiladi,
   ishlatilgan imzoni qisqa muddat qayd qilib, takroran ishlatishni va so‘rovlar tezligini
   cheklaydi; mijoz yuborgan Telegram ID’ga ishonmaydi. Kirgandan keyin bazadan
   foydalanuvchini qayta topib, bloklangan
   emasligini va o‘qituvchi rolini tekshiradi.
6. `/api/panel/link` bir martalik kirish havolasini Mini App’dan so‘rash uchun mavjud endpoint bo‘lib
   qoladi. Uchinchi tomon widgeti yoki yangi endpoint qo‘shilsa, xavfsizlik va
   autentifikatsiya oqimi alohida test qilinadi.

Faol sessiyalar ro‘yxati va amallar uchun yangi, `owner_id` bilan cheklangan endpointlar
kerak bo‘ladi: joriy foydalanuvchining sessiyalarini ko‘rish, bitta sessiyani bekor qilish
va barcha sessiyalarni bekor qilish. Yo‘llar implementatsiya PR’ida panel API naqshiga
moslanadi; har bir amalda `user_id` serverda aniqlanib, so‘rov tanasidagi egasiga
ishonilmaydi.

Sessiya cookie’si o‘g‘irlangan bo‘lsa, u bekor qilinmaguncha yoki muddati tugamaguncha
ishlatilishi mumkin. Shu sababli token faqat xesh ko‘rinishida saqlanadi, bekor qilish
darhol tekshiriladi, qurilma belgisi esa sir sifatida qaralmaydi. Har bir o‘zgarishda
`tests/test_panel.py` kengaytirilib, xesh saqlanishi, muddati tugash, bitta sessiyani va
barcha sessiyalarni bekor qilish, boshqa foydalanuvchi sessiyasiga kira olmaslik,
eski token o‘tish muddati, CSRF/Origin, bloklangan o‘qituvchi va Telegram Login Widget
imzo tekshiruvi sinovdan o‘tkaziladi. Yangi migratsiya uchun bo‘sh PostgreSQL’da qo‘llash, orqaga qaytarish va qayta qo‘llash
tekshiruvi qo‘shiladi; ishlab chiqarish ma’lumotlari bilan mashq qilinmaydi.

## C. Planshet va desktop UX

### Hozirgi holat

`panel.css` desktop’da 240 px chap menyu va asosiy kontent ustunidan foydalanadi.
`theme.css` yorug‘ va qorong‘i mavzularni, `:focus-visible` konturini, ekran o‘quvchi uchun
skip-link’ni va semantik jadvallarni qo‘llaydi. Jadval `.pn-table-wrap` orqali gorizontal
siljiydi; telefon o‘lchamida `.pn-only-wide` jadvali kartali ro‘yxat bilan almashadi.
Katta boshqaruv tugmalari, menyu, matn maydonlari va davomat belgilari 44 px.

### Kamchilik va takliflar

- `768–1100 px` oralig‘ida menyu hanuz 240 px; asosiy kontent torayadi. Shu oraliqda
  jadvalning muhim ustunlari va yetti kunlik jadval kataklari siqilishi mumkin. Planshet
  uchun alohida sinov va moslashuv rejasi kerak; jadvaldagi ikkinchi darajali ustunlarni
  yashirish yoki gorizontal siljitish, haftalik jadvalni esa tushunarli gorizontal
  ko‘rinishga o‘tkazish ko‘rib chiqiladi.
- Telefon uchun breakpoint 760 px, KPI va ayrim ikki ustunli bloklar 1100 px da
  o‘zgaradi. 768, 900, 1024, 1100 va 1280 px da matn kesilishi, sahifadan tashqariga
  chiqish, jadvaldagi amal ustuni va sarlavha amallari qabul sinovidan o‘tadi.
- `.pn-btn-sm` va `.pd-chip` 40 px, `.pd-pill` 32 px balandlikda. Ular bosiladigan
  element bo‘lgani uchun 44 px nishon talabiga moslashtiriladi; `.pd-tag` va `.pn-tag`
  holat belgisi bo‘lib, bosilmaydi. Ularning balandligi o‘zicha 44 px bo‘lishi shart emas.
- `.pn-switch a` ning balandligi 36 px, telefon ko‘rinishida `.pd-mark` tugmasining
  eni 40 px. Ikkalasini ham kamida 44 × 44 px bosish nishoniga moslashtirish kerak.
- Klaviatura fokusi va skip-link bor; yangi modal va amallar uchun Tab/Shift+Tab,
  Enter/Space, Escape, fokusni modalga olib kirish/qaytarish, `aria-live` xato/xabar va
  tugma nomlari alohida tekshiriladi.
- Ko‘rinish faqat desktop’ga emas, 768–1280 px planshet kengligiga mo‘ljallanadi.
  Jadvalning mobil kartali ko‘rinishi saqlanadi; katta ekranda jadval sarlavhasi,
  ustun ma’nosi va amallar ochiq qoladi.

### Rang va o‘lcham tokenlari taklifi

Yangi palitra ixtiro qilinmaydi. `theme.css` dagi yagona binafsha aksent — OKLCH rang
doirasi 274 — asosiy brend rangi bo‘lib qoladi. Yashil, sariq va qizil faqat muvaffaqiyat,
ogohlantirish va xavf holatlari uchun ishlatiladi.

| Token | Hozirgi qiymat yoki rol | Faza 2 taklifi |
|---|---|---|
| `--accent` | Light `#4450a8`, dark `#a0b0f4`; zamonaviy brauzerda OKLCH hue 274 | Asosiy tugma, fokus va faol navigatsiya uchun yagona binafsha token sifatida saqlash |
| `--accent-ink` | Light `#f9fafd`, dark `#0f1223` | Aksent ustidagi matn kontrastini saqlash |
| `--accent-soft` | Aksentni kartaga 16% aralashtirish | Tanlangan qator va yengil holatlar uchun, qo‘lda boshqa binafsha kiritmaslik |
| `--bg`, `--card` | Light `#f6f3ef` / `#fffdfb`; dark `#0e1017` / `#161921` | Sahifa va sirt ranglarini mavzu tokenlaridan olish |
| `--fg`, `--muted` | Light `#161a25` / `#535862`; dark `#f4f1ed` / `#9fa5af` | Asosiy va ikkilamchi matn kontrastini saqlash |
| `--nav-border` | Light `#dbd7d1`, dark `#2c3039` | Jadval va kartalardagi ajratgich uchun bitta token |
| `--success`, `--warning`, `--danger` | Holatga oid semantik ranglar | Faqat natija va xavf holatlarida; brend ranglari sifatida ishlatmaslik |
| `--space-1`…`--space-8` | `4, 8, 12, 16, 24, 32, 40, 48 px` | Paneldagi takroriy qattiq oraliqlarni umumiy tokenlarga ulash |
| `--radius-sm`, `--radius`, `--radius-lg`, `--radius-inner` | `14, 18, 20, 10 px` | Paneldagi takroriy burchaklarni umumiy radius tokenlariga ulash |
| `--font`, `--fs-xs`…`--fs-xl` | Tizim shriftlari; `12, 13, 16, 20, 24 px` | Mavjud shrift va o‘lcham tokenlarini yagona manba sifatida ishlatish; paneldagi qattiq qiymatlarni bosqichma-bosqich ulash |

`panel.css` ranglar uchun mavzu tokenlarini ishlatadi, lekin oraliq, radius va ayrim
interaktiv balandliklar qattiq yozilgan. Taklif: mavjud `theme.css` tokenlarini yagona
manba qilish; rang, oraliq va radiusni `panel.css` ichida ikkinchi marta belgilamaslik.

## D. O‘qituvchini panelga yo‘naltirish

- Mini App’da o‘qituvchi kabineti ochiq qoladi. `summary.js` dagi `panelCard()` hozir
  kabinet sahifasining yuqori qismida turadi va `/api/panel/link` orqali botga bir martalik
  havola yuboradi. Uni asosiy, aniq “Panelni ochish” tugmasi sifatida kuchaytirish;
  Mini App kabinetini ikkilamchi “Telefon kabineti” yo‘li sifatida saqlash taklif qilinadi.
- Botning o‘qituvchi asosiy menyusidagi `menu_teach` hozir Mini App kabinetini ochadi.
  Birinchi amal panelga bir martalik havola so‘rash bo‘ladi; Mini App’ni ochish tugmasi
  ikkinchi darajali bo‘lib qoladi. Mavjud `/panel` buyrug‘i zaxira yo‘l sifatida saqlanadi.
- O‘qituvchiga yuboriladigan so‘rov va davomat xabarlaridagi `cabinet_markup` hozir
  Mini App’ni ochadi. Xabarga birinchi “Panelni ochish” callback amali qo‘shilib, u
  mavjud `panel_login.send_link()` xizmatidan foydalanib alohida, bir martalik havolani
  shaxsiy chatga yuboradi; Mini App tugmasi ikkinchi amal bo‘lib qoladi. Callback faqat
  xabar egasining o‘qituvchi ekanini server tomonda tekshiradi.
- Mini App’da havola so‘ralgandan keyin aniq “Botga havola yuborildi” holati va yuborish
  xatosi ko‘rsatiladi. Kirilmagan yoki o‘qituvchi bo‘lmagan foydalanuvchiga panel tokeni
  yoki boshqa egaga tegishli ma’lumot oshkor qilinmaydi.
- O‘quvchining `study` yuzasi va botdagi o‘quvchi tugmalari o‘zgarmaydi. Har bir yangi
  matn Mini App va bot uchun uz/ru/en tarjimalarida bo‘ladi.

## E. Alohida PR bo‘laklari

Quyidagi tartib kichik va qaytarilishi oson UI ishlaridan, keyin ma’lumot va sessiya
xavfi yuqoriroq ishlarga qarab tuzildi. Hech bir PR boshqa PR’ni avtomatik birlashtirmaydi.

| Tartib | PR vazifasi | Hajm | Xavf | Asosiy tekshiruv |
|---|---|---|---|---|
| 1 | Panel UI uchun Playwright sinov to‘plami va CI ishini qo‘shish | M | O‘rta: yangi brauzer vositasi, paket va CI vaqti | Panel sahifasini ochish, asosiy amallar, 768/1024/1280 px va klaviatura |
| 2 | Panel UI tayanchi: tokenlardan foydalanish, bosiladigan 40/32 px elementlarni 44 px ga yetkazish, 768–1280 px jadval va haftalik jadvalni tekislash | M | Past-o‘rta: CSS o‘zgarishi sahifalararo ta’sir qilishi mumkin | Yorug‘/qorong‘i mavzu; klaviatura va rang kontrasti |
| 3 | O‘qituvchi uchun panelni ochish tugmasini Mini App, bot menyusi va o‘qituvchi bildirishnomalarida asosiy qilish | M | O‘rta: bir martalik havola yuborilishi va rolga bog‘liq | `tests/test_panel.py`, bot handler testlari, Mini App tarjima/paritet testi, o‘qituvchi va o‘quvchi rollari |
| 4 | Guruh va o‘quvchini tasdiq bilan o‘chirish | S–M | O‘rta-yuqori: qaytarib bo‘lmaydigan amal va bog‘liq ma’lumotlar | API egalararo 404; tasdiq/bekor qilish; bog‘liq qatorlar xatti-harakati |
| 5 | Paneldan yakka dars yaratish | M | O‘rta: Toshkent vaqti, sana chegarasi, ixtiyoriy o‘quvchi | API va panel yaratish/tahrirlash; vaqt chegarasi; egalararo 404 |
| 6 | Panelda qo‘lda eslatma yaratish/boshqarish | M | O‘rta: rejalashtirilgan yuborish va takroriy yuborish | API yaratish/o‘chirish; yuborish vaqti; egalararo 404; yuborilgan holat |
| 7 | Mavzu va uy vazifasini paneldan boshqarish | M–L | O‘rta-yuqori: guruh, mavzu va muddat bog‘lanishi | API tekshiruvi; saqlash/qayta o‘qish; egalararo 404; bo‘sh holat |
| 8 | Sessiya jadvali va orqaga mos migratsiya; bir martalik havoladan bekor qilinadigan sessiyaga o‘tish | L | Yuqori: kirish, cookie va migratsiya xatari | Bo‘sh PostgreSQL’da migratsiya; xesh, muddat, eski token, Origin/CSRF, bekor qilish |
| 9 | “Meni eslab qolish”, faol qurilmalar va bitta yoki barcha sessiyalarni bekor qilish | M–L | Yuqori: o‘g‘irlangan cookie muddati va chiqish ishonchliligi | Harakatsizlik/mutlaq muddat; parallel so‘rov; foydalanuvchilararo ajratish; barcha qurilmadan chiqish |
| 10 | Telegram Login Widget’ni zaxira kirish yo‘li sifatida qo‘shish | L | Yuqori: imzo, takroran ishlatish, domen va akkaunt bog‘lanishi | BotFather domeni; HMAC/`auth_date`; eskirgan va o‘zgartirilgan ma’lumot; bloklangan yoki o‘qituvchi bo‘lmagan foydalanuvchi |

### Qabuldan oldingi tasdiqlar

- “Meni eslab qol” uchun taklif qilingan 30 kunlik harakatsizlik va 90 kunlik mutlaq
  muddatni tasdiqlash yoki o‘zgartirish.
- Planshetda haftalik jadvalni gorizontal siljitish yoki boshqa ixcham ko‘rinishda
  berishdan qaysi biri afzal ekanini belgilash.
- Zaxira kirish uchun Telegram Login Widget domenini BotFather’da ro‘yxatdan o‘tkazish
  va boshqarish mas’ulini belgilash.
