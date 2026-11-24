# Egasi (super admin) sahifasi rejasi

- Holat: egasi sahifasi va uning UI’i hali reja. To‘lov qarorlarini
  `audit_logs`-ga yozish xizmat qismi alohida PR’da bajarildi; panel xatti-harakati
  va qolgan bo‘laklar hali amalga oshirilmagan.
- Asosiy yuza: egasi mijoz obunalarini kompyuter va planshetdagi `/panel` orqali
  boshqaradi. Mini App dagi mavjud `#/admin` telefon zaxirasi bo‘lib qoladi.
- Foydalanuvchiga ko‘rinadigan barcha yangi matnlar uz/ru/en tarjima qilinadi.

## 1-bosqich: MVP

| Qism | Mavjud xizmat yoki API | Kerakli panel xatti-harakati | Sinov rejasi |
|---|---|---|---|
| To‘lov navbati | `GET /api/admin/payments?status=queue`, `GET /api/admin/payments/{id}`, `GET /api/admin/payments/{id}/receipt` | Navbatni sana va holat bilan ko‘rsatish; to‘lov kodi, summa, tarif/davr va karta oxirgi 4 raqamini solishtirish; chekni alohida tugma bilan ochish; takroriy chek, soxta chek belgisi va mijozning oldingi belgilarini ko‘rsatish. Summa yoki kodni avtomatik tanish hozir yo‘q; birinchi talqinda admin qo‘lda tekshiradi. | HTTP ruxsat matritsasi; to‘lov kodi va summasini tekshirish; chek tugmasi bosilmaguncha fayl olinmasligi; ayni `receipt_unique_id` takrorligini ko‘rsatish; so‘rovlarda 403/401; o‘zgarish uchun `audit_logs` qatori |
| To‘lov qarorlari | `POST .../approve`, `POST .../reject`, `POST .../fake` | Tasdiqlash, rad va soxta belgilashda aniq tasdiq so‘rash; sabab kiritish talablarini saqlash; natijani navbat va mijoz kartasida yangilash. | Har amal uchun xizmat va HTTP sinovi; `PaymentEvent` saqlanishi bilan birga `audit_logs` yozuvi; qayta yuborilgan amalni takroran qo‘llamaslik; bildirishnoma xatosini qaror muvaffaqiyatidan ajratish |
| Mijozlar ro‘yxati | `GET /api/admin/tenants?q=...` | Ism, foydalanuvchi nomi va Telegram ID qidiruvi; tarif, to‘lov/akkaunt holati va muddat yaqinligi bo‘yicha filtr; har qatorda holat, tarif va tugash sanasi. Hozirgi 50 qatorlik chegarani o‘sishga moslash kerak; yangi sahifalash javob shaklini o‘zgartirsa, koddan oldin alohida kelishiladi. | Qidiruv va filtr birikmalari; bo‘sh va natijali holat; muddat chegarasi; super admin bo‘lmagan foydalanuvchiga 403; sahifalash bo‘lsa takrorlanmagan va tushib qolmagan qatorlar |
| Mijoz kartasi | `GET /api/admin/tenants/{user_id}`; grant, extend va payment-block API’lari | Obuna/to‘lov tarixi, joriy foydalanish, tarif berish/uzaytirish, akkauntni bloklash va ichki izoh. To‘liq akkaunt bloklash uchun `AdminService.set_blocked`ni tekshiradigan alohida admin amali kerak. `payments_blocked` (to‘lov boshlash taqiqi) va `is_blocked` (akkauntdan foydalanish taqiqi) alohida nom va tasdiq bilan ko‘rsatiladi. Oylik AI/bildirishnoma kvotasi hamda chat/guruh/o‘quvchi soni tarif cheklovlari bilan taqqoslanadi. | Boshqa mijoz ID’si bo‘yicha huquq tekshiruvi; tarix va limit hisoblari; har bir yozuvchi amal uchun audit qatori; to‘liq akkaunt bloklanganda kirish rad etilishi; to‘lov bloki faqat to‘lov oqimiga ta’sir qilishini tekshirish |
| Tarifni boshqarish | Hozirgi `grant` va `extend` xizmatlari | Tarif va muddatni tanlash, sababni majburiy kiritish, amal oldidan yakuniy tasdiq; muvaffaqiyatdan so‘ng yangi holatni ko‘rsatish. | Mavjud tekshiruv, noto‘g‘ri tarif/kun, muddati tugagan obuna, muvaffaqiyat va `audit_logs` ma’lumoti |
| Ichki izoh | Maxsus ustun yoki jadval yo‘q; `audit_logs.data` JSONB bor | Taklif: izohni yangi `owner_note_changed` audit hodisasiga qo‘shimcha yozuv sifatida saqlash va oxirgi hodisani joriy izoh deb ko‘rsatish. Shunda har bir tahrir tarixda qoladi va yangi migratsiya kerak bo‘lmaydi. Saqlash/o‘chirish tartibi va izoh uzunligi koddan oldin tasdiqlanadi. | Super admin bo‘lmagan foydalanuvchiga 403; izoh faqat admin uchun; har tahrirda yangi audit qatori; ortiqcha uzun matn rad etilishi; izohda to‘liq karta raqami yoki maxfiy qiymat bo‘lmasligi |
| Audit jurnali | `GET /api/admin/audit`, `audit_logs`, `payment_events` | Amal bajaruvchi, vaqt, obyekt, amal, sabab va oldingi/keyingi qiymatni ko‘rsatish; foydalanuvchi hamda to‘lov bo‘yicha filtrlash. Hozirgi to‘lov qarorlarining `PaymentEvent` tarixini `audit_logs`-ga ham yozish kerak. | Tarif, uzaytirish, to‘liq blok, to‘lov qarori va izoh uchun `audit_logs` yozuvini tekshirish; hodisani actor/entity bilan bog‘lash; audit ro‘yxatini to‘g‘ri tartiblash |

### Kirish

Egasi sahifasini faqat `SUPER_ADMIN_IDS` ro‘yxatidagi Telegram ID ochadi. Hozirgi
`/panel` bir martalik havolasini faqat o‘qituvchi oladi; odatiy panel tokeni 12 soatlik
stateless imzolangan cookie. Egasi uchun o‘qituvchi cookie’sidan alohida kirish va
sessiya kerak.

| Tanlov | Afzallik | Xavf va kamchilik |
|---|---|---|
| Hozirgi stateless token bilan boshlab, keyin Faza 2 sessiya jadvaliga ko‘chish | Yangi jadvalni kutmaydi, boshlang‘ich ish kamroq | Bitta tokenni serverdan darhol bekor qilib bo‘lmaydi; 8 soat o‘tishi yoki ID `SUPER_ADMIN_IDS` ro‘yxatidan olinishi bilan foydalanish to‘xtaydi. Hozirgi tokenda mo‘ljal belgisi yo‘q, shu sababli alohida cookie va owner yo‘li tekshiruvi shart. Keyin ikkinchi kirish usulini qo‘shish va qayta ko‘chirish xavfi bor. |
| Faza 2 server sessiya jadvalini kutish | Token xeshi, qurilma belgisi, oxirgi faollik, muddat va bekor qilish bitta shaklda; owner va teacher maqsadini ajratish, qurilma yoki barcha sessiyalarni bekor qilish mumkin | Bog‘liq migratsiya va koddan oldin Faza 2 sessiya ishiga alohida ruxsat kerak; owner sahifasi kechroq boshlanadi. |

**Tavsiya:** Ikkinchi usulni tanlab, Faza 2 sessiya jadvali ishiga ruxsat olish va
jadvaldagi `owner_admin` maqsadini teacher sessiyasidan ajratishni shu ish doirasida
kelishish. Owner kirish havolasi ham alohida maqsadga ega bo‘ladi. Jadval yoki havola
uchun zarur o‘zgarish faqat yangi jadval/ustun qo‘shadi; mavjud teacher ma’lumoti,
cookie yoki havolani o‘zgartirmaydi. Migratsiya PR’i kod PR’idan oldin egasi tomonidan
birlashtiriladi.

Owner sessiyasi uchun mo‘ljallangan shartlar:

- Kirish va sessiya berish vaqtida Telegram ID `SUPER_ADMIN_IDS` ro‘yxatida ekanini
  server tekshiradi; har bir owner API so‘rovida ruxsat qayta tekshiriladi.
- Bir martalik havola qisqa muddatli bo‘ladi; muvaffaqiyatli kirishdan keyingi sessiya
  **8 soat mutlaq muddatli**, “meni eslab qol” va avtomatik uzaytirishsiz.
- Teacher’ning `ritm_panel` cookie’sidan farqli cookie va sessiya maqsadi ishlatiladi;
  owner tokeni teacher kirish yo‘lida qabul qilinmaydi.
- Cookie `HttpOnly`, `Secure`, `SameSite=Lax` bo‘ladi. Chiqish, sessiyani bekor qilish
  va o‘zgartiruvchi so‘rovlarda mavjud `Origin`/CSRF tekshiruvi va so‘rov cheklovi qoladi.
- Sessiya bazasini tekshirish muvaffaqiyatsiz bo‘lsa, xavfsizlik uchun owner API rad
  etiladi; xato muvaffaqiyatdek ko‘rsatilmaydi.
- Telegram Login Widget bu rejaga kirmaydi; doimiy domen va alohida ruxsatsiz
  `/setdomain` sozlanmaydi.

### Maxfiylik va o‘zgarishlar jurnali

- Mijoz ro‘yxati va kartasida to‘liq karta raqami bo‘lmaydi; mavjud
  `payer_card_last4` qiymatidan faqat oxirgi 4 raqam ko‘rsatiladi.
- Chek rasmi/fayl ID’si brauzerga qaytarilmaydi. Mavjud himoyalangan receipt API
  alohida tugma bosilganda faylni uzatadi; Telegram fayl manzili va bot tokeni
  oshkor qilinmaydi.
- Tarif berish/uzaytirish, to‘lovni tasdiqlash/rad etish/soxta belgilash, akkaunt va
  to‘lov bloklari hamda ichki izoh kabi har bir o‘zgartiruvchi amal shu tranzaksiyada
  `audit_logs`-ga yoziladi. To‘lovning `payment_events` tarixi ham saqlanadi.
- Audit yozuvida bajaruvchi, vaqt, amal, obyekt va sabab bo‘ladi. Izohda maxfiy
  qiymat yoki karta ma’lumoti saqlanmaydi.

### Ruxsat va ma’lumot ajratish sinovlari

- Har bir yangi owner API endpoint uchun kirishsiz so‘rov `401`, super admin bo‘lmagan
  haqiqiy foydalanuvchi so‘rovi `403` bo‘lishini tekshirish.
- Har bir yozuvchi amal uchun `audit_logs` qatori aynan bir marta va asosiy o‘zgarish
  bilan bitta tranzaksiyada saqlanishini tekshirish.
- Mavjud `tests/test_tutor_tenant_matrix_http.py` matritsasini zaiflashtirmaslik;
  owner admin yo‘llari tutor endpointlarining `owner_id` chegarasini chetlab o‘tmasin.
- UI tekshiruvida 768, 900, 1024, 1100 va 1280 px; klaviatura bilan yurish, fokus,
  tasdiq oynalari, xato/bo‘sh holat va yorug‘/qorong‘i mavzularni qamrash.

## 2-bosqich: keyingi imkoniyatlar

| Imkoniyat | Kerakli ish | Mavjud ma’lumot va yangi ehtiyoj |
|---|---|---|
| Platforma ko‘rsatkichlari | MRR, haqiqiy tushum, faol sinov, pullik tarifga o‘tish, mijoz ketishi va kvota ko‘rinishlarini aniq ta’riflash | MRR, tushum, tugash va hozirgi kvota ko‘p jihatdan mavjud jadvallardan chiqadi. Sinovdan pullikka o‘tish uchun vaqt oralig‘i va aniq bog‘lovchi hodisa kerak; joriy `started_at`-ga asoslangan `new_paid` bu o‘lchovni ishonchli bermaydi. |
| Obuna hayot sikli | Tarif boshlanishi, uzayishi, tugashi, bekor bo‘lishi, grant va to‘lov o‘zgarishlari tarixini aniq belgilash | Mavjud `subscriptions`, `payments`, `payment_events` tarixning bir qismini beradi. Yangi holat/hodisa kerak bo‘lsa, faqat qo‘shuvchi migratsiya alohida PR bo‘ladi. |
| Mijozga qo‘lda eslatma | Mijozga botdan tarif tugashi yoki to‘lov haqida bir martalik xabar yuborish | Bot xabari mumkin; yuborish limiti, audit, tarjima, yetkazilmagan holat va takroriy yuborishni oldini olish qoidasi kerak. |
| Tizim holati | Baza, bot webhooki, scheduler va navbatning joriy holatini ko‘rsatish | Hozirgi overview ayrim xatoli ishlarni, `/health` esa bazaga ulanishni tekshiradi. Scheduler/webhookning tirikligini ishonchli ko‘rsatish uchun yurak urishi yoki tashqi kuzatuv ma’lumoti kerak bo‘lishi mumkin. |

## Alohida PR bo‘laklari

Bo‘laklar hajm bo‘yicha kichikdan kattaga berilgan. Ishni bajarish tartibida autentifikatsiya
va migratsiya boshqa ekranlardan oldin keladi. Migratsiya kerak bo‘lsa, avval faqat
qo‘shuvchi migratsiya PR’i ochiladi; uni egasi birlashtirgandan keyin undan foydalanadigan
kod PR’i ochiladi. Hech bir PR avtomatik birlashtirilmaydi.

| Hajm | Alohida PR vazifasi | Xavf | Migratsiya |
|---|---|---|---|
| S | To‘lov qarorlari uchun `audit_logs` yozuvini qo‘shish | O‘rta: auditda yo‘q yoki takror qator | Yo‘q; mavjud `payment_events` ham saqlanadi |
| S–M | Ichki izohni `owner_note_changed` audit hodisasi sifatida yuritish | O‘rta: xususiy matnni ko‘rish va saqlash | Yo‘q; `audit_logs.data` ishlatiladi, o‘chirish tartibi oldindan tasdiqlanadi |
| S–M | Owner sessiyasi va bir martalik kirish havolasi uchun qo‘shimcha jadval/ustun | Yuqori: autentifikatsiya ma’lumoti | Ha, alohida qo‘shuvchi PR; eski teacher qatorlari o‘zgarmaydi |
| M | Owner panelga alohida kirish nuqtasi va boshlang‘ich sahifa | O‘rta-yuqori: teacher sahifasidan ajratish | Sessiya migratsiyasi birlashtirilgan bo‘lishi shart |
| M | To‘lov navbatining o‘qish ko‘rinishi va chekni alohida ochish | O‘rta: moliyaviy ma’lumot ko‘rinishi | Yo‘q |
| M | Mijozlar ro‘yxatiga tarif, holat va tugash yaqinligi filtrlarini qo‘shish | O‘rta: ro‘yxat so‘rovi va ishlash tezligi | Yo‘q; javob shakli o‘zgarsa oldindan tasdiq olinadi |
| M | Mijoz kartasida obuna/to‘lov tarixi va kvotalarni ko‘rsatish | O‘rta: ko‘rsatkichlarni noto‘g‘ri talqin qilish | Yo‘q |
| M | Tarif berish va uzaytirishni desktop panelga ulash | O‘rta-yuqori: obunaga ta’sir | Yo‘q; mavjud xizmat va audit ishlatiladi |
| M | To‘liq akkauntni bloklash/bekor qilish amallarini panelga qo‘shish | Yuqori: foydalanuvchi tizimga kira olmay qolishi | Yo‘q; `users.is_blocked` mavjud |
| M | Owner audit oynasida foydalanuvchi va to‘lov bo‘yicha izlash/filtr | O‘rta: audit qatorlari ko‘payishi | Yo‘q |
| M | MRR va tushum ko‘rsatkichlarini ta’riflangan davrlar bo‘yicha ko‘rsatish | O‘rta: moliyaviy hisobni noto‘g‘ri talqin qilish | Ehtimol yo‘q; ma’lumot yetmasa qo‘shimcha migratsiya alohida PR |
| M | Mijozga bot orqali qo‘lda eslatma yuborish | O‘rta-yuqori: takroriy yoki noto‘g‘ri xabar | Takrorlanmaslik uchun yangi doimiy yozuv kerak bo‘lsa, alohida PR |
| M–L | Sinovdan pullikka o‘tish ko‘rsatkichining aniq ta’rifi va hodisasini qo‘shish | Yuqori: eski ma’lumotdan noto‘g‘ri xulosa | Ehtimol ha; faqat yangi ustun/jadval, alohida PR |
| M–L | Tizim va scheduler holatini kuzatish | Yuqori: eskirgan yoki noto‘g‘ri holat ko‘rsatish | Yurak urishini saqlash uchun yangi jadval/ustun kerak bo‘lsa, alohida PR |
| L | `SUPER_ADMIN_IDS` bilan tekshiriladigan, 8 soatlik owner login va bekor qilinadigan server sessiyasi | Yuqori: cookie, CSRF va noto‘g‘ri rol berish | Oldingi sessiya migratsiyasi birlashtirilgan bo‘lishi shart |
| L | Obuna hayot sikli boshqaruvi | Yuqori: tarif va to‘lov holati | Qoidaga qarab; kerak bo‘lsa alohida qo‘shuvchi PR |

## Faza 2 panel PR’lari bilan to‘qnashish xavfi va navbat

Hozir PR #11 ochiq; u `app/webapp/static/panel.css` va
`tests/test_panel_layout.py` fayllarini o‘zgartiradi. Bu hujjat PR’i ular bilan
to‘qnashmaydi. Owner panelining amaliy ishi `panel.css`, panel kirishi, autentifikatsiya,
API ruxsat tekshiruvi va layout sinovlariga tegishi mumkin.

Tavsiya etiladigan tartib:

1. PR #11’ni egasi ko‘rib, birlashtirishini kutish; bu ish doirasida uni birlashtirmaslik.
2. Faza 2 panel CSS poydevori va o‘qituvchini yo‘naltirish ishlarini owner panel
   ko‘rinishidagi o‘zgarishlar bilan bir vaqtda bajarmaslik.
3. Owner autentifikatsiyasi Faza 2 sessiya jadvaliga bog‘liq. U ishni boshlash uchun
   alohida ruxsat kerak; bu reja o‘zi bajarishga ruxsat bermaydi.
4. To‘qnashuvni kamaytirish uchun owner backendini alohida route/service moduliga,
   owner ekranini alohida JavaScript/CSS moduliga ajratish taklif qilinadi. Kirish
   yo‘li, endpoint kelishuvi yoki jadval tuzilishini o‘zgartirishdan oldin egasining
   roziligi olinadi.

## Amalga oshirishdan oldin egasi hal qiladigan savollar

1. `payments_blocked`-dan alohida to‘liq `is_blocked` boshqaruvi owner panelda
   bo‘lishini tasdiqlash.
2. Ichki izohni `audit_logs` qo‘shimcha tarixida saqlab, oxirgi qatorni joriy izoh
   deb olishni tasdiqlash yoki maxsus jadval so‘rash.
3. Owner login uchun Faza 2 sessiya jadvali ishini boshlashga alohida ruxsat berish.
