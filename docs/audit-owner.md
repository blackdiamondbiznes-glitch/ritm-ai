# Egasi (super admin) yuzasi auditi

- Holat: kodni o‘qib tayyorlangan audit; bu ishda kod o‘zgartirilmagan.
- Maqsad: mavjud admin imkoniyatlarini paneldagi kelajakdagi egasi sahifasi bilan
  solishtirish.
- Sinov holatida HTTP sinovlari va brauzer sinovlari alohida ko‘rsatiladi.

## Mavjud admin API

Barcha `/api/admin/*` manzillar serverda `SUPER_ADMIN_IDS` bilan tekshiriladi.
Oddiy foydalanuvchiga `403`, kirish ma’lumoti yo‘q so‘rovga `401` qaytarilishi
`tests/test_admin_http.py` dagi ruxsat matritsasida tekshiriladi.

| Manzil | Vazifasi | Kim uchun | Sinov holati |
|---|---|---|---|
| `GET /api/admin/overview` | Mijoz, faol obuna, tushum, MRR, to‘lov navbati, xatoli ishlar va AI ishlatilishini jamlaydi | Faqat super admin | Ruxsat matritsasi va asosiy ko‘rsatkichlar tekshirilgan |
| `GET /api/admin/tenants?q=...` | Chat, obuna yoki to‘lov yozuvi bor mijozlarni ism, foydalanuvchi nomi yoki Telegram ID bo‘yicha qidiradi | Faqat super admin | Ruxsat matritsasi bor; qidiruvning barcha chekka holatlari alohida tekshirilmagan |
| `GET /api/admin/tenants/{user_id}` | Mijoz, joriy tarif, chat, obuna va to‘lov tarixini ko‘rsatadi | Faqat super admin | Ruxsat matritsasi va ayrim o‘zgarishlardan keyingi javob tekshirilgan |
| `POST /api/admin/tenants/{user_id}/grant` | Tarifni belgilangan kunlarga beradi; sabab talab qilinadi | Faqat super admin | Ruxsat, noto‘g‘ri so‘rov, muvaffaqiyatli amal va audit yozuvi tekshirilgan |
| `POST /api/admin/tenants/{user_id}/extend` | Ochiq obunani belgilangan kunga uzaytiradi | Faqat super admin | Ruxsat, noto‘g‘ri so‘rov, muvaffaqiyatli amal va audit yozuvi tekshirilgan |
| `POST /api/admin/tenants/{user_id}/payments-block` | Faqat yangi to‘lov boshlashni taqiqlaydi yoki qayta yoqadi | Faqat super admin | Ruxsat va o‘zgartirish oqimi tekshirilgan; bu to‘liq akkaunt bloklash emas |
| `GET /api/admin/payments?status=...` | To‘lovlarni holat bo‘yicha ro‘yxatlaydi | Faqat super admin | Ruxsat matritsasi bor; har bir filtr natijasi alohida to‘liq tekshirilmagan |
| `GET /api/admin/payments/{payment_id}` | To‘lov tafsiloti, hodisalar, takroriy chek va mijoz belgilarini beradi | Faqat super admin | Ruxsat va to‘lov hodisalari tekshirilgan |
| `GET /api/admin/payments/{payment_id}/receipt` | Chekni bot orqali olib, API javobi sifatida uzatadi; Telegram manzilini ochmaydi | Faqat super admin | Ruxsat, proksi va kesh oqimi tekshirilgan |
| `POST /api/admin/payments/{payment_id}/approve` | To‘lovni tasdiqlaydi va mijozga xabar yuboradi | Faqat super admin | Ruxsat, muvaffaqiyat, takroriy qaror va to‘lov hodisasi tekshirilgan |
| `POST /api/admin/payments/{payment_id}/reject` | Sabab bilan to‘lovni rad etadi | Faqat super admin | Ruxsat, sabab tekshiruvi va to‘lov hodisasi tekshirilgan |
| `POST /api/admin/payments/{payment_id}/fake` | Chekni soxta deb belgilaydi; takroriy holatlarni ham hisobga oladi | Faqat super admin | Ruxsat, belgi, takroriy chek va to‘lov blokiga ta’siri tekshirilgan |
| `GET /api/admin/chats?q=...` | Chatlarni nomi, foydalanuvchi nomi yoki Telegram ID bo‘yicha qidiradi | Faqat super admin | Ruxsat matritsasi bor; qidiruv chekka holatlari to‘liq qamralmagan |
| `GET /api/admin/audit` | To‘lov hodisalari, audit yozuvlari va bahsli to‘lovlarni ko‘rsatadi | Faqat super admin | Ruxsat va ayrim yozilgan hodisalar tekshirilgan |
| `GET /api/admin/charts?days=...` | Tushum, tariflar, sinovlar, berilgan tariflar, mijoz ketishi, AI va ishlar grafikasini qaytaradi | Faqat super admin | Ruxsat, grafiklar shakli va hisoblar tekshirilgan |

## Mini App dagi `#/admin` ekranlari

| Ekran | Vazifasi | Kim uchun | Sinov holati |
|---|---|---|---|
| Umumiy ko‘rinish | Platforma hajmi, faol tariflar, tushum, navbat, AI va xatoli ishlar haqida tezkor ko‘rsatkich | Faqat super admin | API sonlari tekshirilgan; statik sinov navigatsiya va tarjima kalitlarini tekshiradi |
| Statistikalar | Oylik tushum, sinov/pullik tarif/grant soni, mijoz ketishi, tariflar kesimidagi faol mijozlar, asoschilar va AI ishlatilishi | Faqat super admin | Grafik API ma’lumoti tekshirilgan; brauzerdagi ko‘rinish sinovi yo‘q |
| To‘lovlar ro‘yxati | Navbat, bahsli, soxta, tasdiqlangan va rad etilgan holatlarni ajratadi | Faqat super admin | API ruxsati tekshirilgan; Mini App uchun to‘liq brauzer sinovi yo‘q |
| To‘lov tafsiloti | Summa, tarif, davr, kod, karta oxirgi 4 raqami, vaqt, chek, takroriy chek va tasdiqlash/rad/soxta amallari | Faqat super admin | API amallari va to‘lov hodisalari tekshirilgan; chek tafsilot ochilishi bilan avtomatik yuklanadi |
| Mijozlar ro‘yxati | Qidiruv, tarif, chatlar soni va amal qilish sanasini ko‘rsatadi | Faqat super admin | API ruxsati bor; tarif, holat va tugash sanasi bo‘yicha filtr yo‘q |
| Mijoz kartasi | Tarif va to‘lov tarixi, chatlar, AI ishlatilishi, tarif berish/uzaytirish va to‘lovni bloklash | Faqat super admin | Grant, uzaytirish va to‘lov bloklash API sinovlari bor; brauzer sinovi yo‘q |
| Chatlar | Platformadagi chatlarni qidirish, egasi va holatini ko‘rish | Faqat super admin | API ruxsati bor; to‘liq brauzer sinovi yo‘q |
| Audit | Audit qatori va bahsli to‘lovlarni ko‘rish | Faqat super admin | API javoblari sinovdan o‘tadi; Mini App uchun to‘liq brauzer sinovi yo‘q |

`tests/test_webapp_static.py` admin tarjimalari va bo‘lim yoqilganini tekshiradi. Admin
Mini App uchun Playwright yoki boshqa brauzer sinovi mavjud emas. Shuning uchun API
sinovidan o‘tganini ekran xatti-harakati to‘liq tekshirildi deb talqin qilib bo‘lmaydi.

## Egasi uchun panelga kirishdagi to‘siq

1. `/panel` sahifasi statik beriladi, ammo kirish uchun bot yuborgan bir martalik havola
   kerak. Havola xeshi bazada saqlanadi, 15 daqiqada eskiradi va bir marta ishlaydi.
2. Havola yuboruvchi `panel_login.is_teacher()` kamida bitta o‘qituvchilik guruhi yoki
   o‘quvchisi borligini talab qiladi. Botdagi `/panel` buyrug‘i hamda
   `POST /api/panel/link` shu tekshiruvni bajaradi. Faqat `SUPER_ADMIN_IDS` ro‘yxatida
   bo‘lib, o‘qituvchi bo‘lmagan egasi havola ololmaydi.
3. Havola ishlatilgach `ritm_panel` nomli `HttpOnly`, `Secure`, `SameSite=Lax` cookie
   beriladi. Uning imzolangan tokeni holatsiz va odatiy muddati 12 soat; serverda
   bekor qilinadigan sessiya yozuvi yo‘q.
4. Panel bosh sahifasi foydalanuvchini `teacher` deb belgilaydi. `panel.js` bu qiymat
   yolg‘on bo‘lsa o‘qituvchi bo‘lmagan holatni ko‘rsatib, panel ish oqimini to‘xtatadi.
5. Mini App dagi admin oqimi bundan alohida: Telegram `initData` tekshiriladi, keyin
   har bir `/api/admin/*` so‘rovi `SUPER_ADMIN_IDS` bilan qayta tekshiriladi. Panelga
   yangi kirish oqimi Mini App dagi admin cheklovini susaytirmasligi kerak.
6. Cookie bilan yuboriladigan o‘zgaruvchi so‘rovlar `Origin`/CSRF tekshiruviga va
   foydalanuvchi bo‘yicha so‘rov chekloviga ega. Yangi egasi oqimida ham shu himoyalar
   saqlanishi shart.

## Ma’lumotlar va ko‘rsatkichlar

| Jadval yoki model | Hozirgi ma’lumot |
|---|---|
| `users` | Telegram ID, ism, foydalanuvchi nomi, yaratilgan/so‘nggi faollik vaqti, `trial_used_at`, `is_blocked`, `payments_blocked`, asoschi belgisi |
| `plans` | Tarif narxi, amal davri, chat/guruh/o‘quvchi va AI/bildirishnoma limitlari |
| `subscriptions` | Egasi, tarif, holat, manba (`trial`, `manual_payment`, `admin_grant`), boshlanish/tugash vaqti, oylik `price_uzs`, to‘langan summa |
| `payments` | So‘ralgan summa, chegirmagacha summa, tarif/davr, holat, tasdiqlash vaqti, to‘lov kodi, chek fayl ID, karta oxirgi 4 raqami, chek takroriyligi |
| `payment_events` | To‘lov qarorlarining qaytarib bo‘lmaydigan hodisa tarixi; qaror, oldingi/keyingi holat, bajaruvchi va qo‘shimcha ma’lumot |
| `usage_counters`, `usage_daily` | Egasi, ko‘rsatkich, oy/kun va son; oylik ko‘rsatkichlar AI yaratish va tutor xabarlarini qamraydi |
| `chats`, tutor guruh va o‘quvchi jadvallari | Faol chat, o‘qituvchi guruhi va o‘quvchilar sonini hisoblash uchun ma’lumot |
| `audit_logs` | Bajaruvchi, amal, obyekt, kichik JSON ma’lumoti va vaqt |

`payment_events` faqat tegishli to‘lovning qo‘shimcha yoziladigan hodisalar tarixidir.
Joriy `PaymentService` to‘lovni tasdiqlash, rad etish va soxta belgilashda
`PaymentEvent` yozadi; bu `audit_logs`-ga ham yozildi degani emas. Tarif berish,
uzaytirish va foydalanuvchini to‘liq bloklash esa `audit_logs` ishlatadi.

| Ko‘rsatkich | Hozirgi ma’lumot bilan hisoblash imkoniyati |
|---|---|
| MRR | Hisoblash mumkin: muddati tugamagan, faol, `manual_payment` manbali obunalarning saqlangan oylik `price_uzs` qiymatini qo‘shish. Admin granti daromad hisoblanmaydi. Bu shu oyning haqiqiy tushumi emas. |
| Haqiqiy oylik tushum | Hisoblash mumkin: `payments` jadvalidagi tasdiqlangan qatorlar `amount_uzs` qiymatini `reviewed_at` oyi bo‘yicha qo‘shish. |
| Tez orada tugaydigan obunalar | Hisoblash mumkin: faol yoki sinov holatidagi obunalarning `expires_at` qiymatini tanlangan vaqt oralig‘i bilan solishtirish. |
| Joriy kvota ishlatilishi | Hisoblash mumkin: oylik `ai_generation` va `tutor_notify` hisoblagichlarini `plans` limitlari bilan solishtirish. Joriy chat, guruh va o‘quvchilar sonini ham tegishli limitlar bilan solishtirish mumkin. |
| Sinovdan pullik tarifga o‘tish | Taxminan hisoblash mumkin: `users.trial_used_at` vaqtini tasdiqlangan to‘lov vaqtiga solishtirish. Ammo o‘tish davri ta’rifi va to‘lovni shu sinov bilan bog‘laydigan alohida hodisa yo‘q. |

Sinov obunasi faol paytda ayni tarif uchun to‘lov tasdiqlansa, `subscriptions` qatori
qayta ishlatiladi va manba `manual_payment` bo‘ladi, lekin `started_at` saqlanib qoladi.
Joriy grafikdagi `new_paid` manba va `started_at` bo‘yicha guruhlanadi; shu sababli
bunday o‘tish to‘lov tasdiqlangan oydan boshqa oyda sanalishi mumkin. O‘tish davri
ta’rifi, ma’lumot tuzilishi va sinovlar kerak.

## Asosiy farqlar va xavflar

- Mijozlar ro‘yxati API hozir `q` qidiruvini oladi va ko‘pi bilan 50 qator qaytaradi.
  Tarif, obuna holati va tugash yaqinligi bo‘yicha filtrlar hamda keyingi sahifaga
  o‘tish imkoniyati yo‘q.
- Mijoz API javobida `is_blocked` maydoni bor, lekin Mini App ro‘yxati va kartasi uni
  to‘liq blok holati sifatida boshqarmaydi. Kartadagi asosiy bloklash amali
  `payments_blocked`-ni boshqaradi. Tizimga kirishni to‘liq taqiqlash va yangi to‘lovni
  taqiqlash turli oqibatga ega; panelda ularni alohida tushuntirib ko‘rsatish kerak.
- Mijozning maxsus ichki izoh maydoni hozircha yo‘q.
- To‘lov tafsiloti ochilganda chek avtomatik yuklanadi. Egasi panelida chekni faqat
  aniq bosilgan amal bilan ochish kerak. Karta uchun mavjud ma’lumot faqat oxirgi
  4 raqam; to‘liq karta raqami ro‘yxatga yoki javobga qo‘shilmasin.
- `overview` vazifa xatosi va qayta urinayotgan ishlarni ko‘rsatadi, lekin bot
  webhooki va schedulerning joriy holatini ishonchli o‘lchamaydi.
- Egasi sahifasi global boshqaruv bo‘lgani uchun `/api/tutor/*` tenant tekshiruvlarini
  o‘zgartirmasligi, boshqa egaga tegishli tutor manzillari uchun mavjud 404 sinovlarini
  saqlashi kerak.
