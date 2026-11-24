# ADR 0003: Jarayon holati va masshtab chegarasi

- Holat: qabul qilindi
- Sana: 2026-11-24

## Kontekst

Production hozir Render Free’da bitta instansiya va Neon Postgres bilan ishlaydi. Bir nechta instansiya yoqilsa yoki deploy vaqtida eski va yangi jarayonlar ustma-ust ishlasa, jarayon xotirasidagi holat umumiy bo‘lmaydi. Panel va Mini App sessiyalari esa serverda saqlanadigan sessiya yozuvlari emas.

## Joriy holat

| Holat | Saqlanish joyi | Qayta ishga tushish va ko‘p instansiya ta’siri |
|---|---|---|
| Aiogram FSM | `MemoryStorage` jarayon xotirasi | Qayta ishga tushganda oqim holati yo‘qoladi; boshqa instansiya oldingi holatni ko‘rmaydi. |
| Tasdiqlanmagan chat takliflari | `PendingChatStore` ichidagi lug‘at | Qayta ishga tushganda yo‘qoladi; instansiyalar o‘rtasida almashilmaydi. |
| So‘rov cheklagichlari | Jarayon ichidagi limit obyektlari | Har instansiya limitni alohida hisoblaydi; qayta ishga tushishda hisoblagichlar tozalanadi. |
| Telegram va ilova keshlari, yuborish oralig‘i | Jarayon ichidagi obyektlar | Instansiyalar keshi va tezlik holati farq qiladi. |
| Mini App va panel sessiyasi | HMAC bilan imzolangan, holatsiz token | Server sessiya yozuvini saqlamaydi; alohida tokenni darhol bekor qila olmaydi. Paneldan chiqish brauzer cookie’sini o‘chiradi, serverdagi tokenni emas. Hozirgi standart amal qilish muddati 12 soat. |
| Rejalashtiruvchi | Har ilova jarayonida APScheduler | Har instansiya o‘z jadval ishlarini ishga tushirishi mumkin. PostgreSQL’dagi ayrim job claim’lari himoyalangan, ammo barcha tick tayyorgarligi bitta atomik claim bilan himoyalanmagan. |

`TELEGRAM_MODE=webhook` production’da bot yangilanishlari va scheduler’ni yoqadi. Render Free xizmati uxlaganda ilova jarayoni to‘xtaydi, shu sababli scheduler uzluksiz ishlashi kafolatlanmaydi.

## `refill_sessions` va `refill_fees` bir vaqtda ishlashini tekshirish

Kod va ma’lumotlar bazasi cheklovlari asosida **takroriy dars yoki hisob yozuvi saqlanmaydi**, ammo ish takroran bajarilishi va tick xato bilan tugashi mumkin.

- `refill_sessions` va `refill_fees` avval `SystemStateRepository.get()`, so‘ng `put()` chaqiradi. Tekshirish va yozish bitta atomik amal emas.
- `tutor_lessons` jadvalida `group_id, planned_at` juftligi uchun qisman yagona indeks bor. `LessonRepository.insert_slot()` PostgreSQL’dagi `ON CONFLICT DO NOTHING` amalidan foydalanadi.
- `tutor_invoices` jadvalida `group_id, student_id, kind, period_start` juftligi uchun yagona cheklov bor. `InvoiceRepository.insert_ignore()` ham `ON CONFLICT DO NOTHING` amalidan foydalanadi. Muddati o‘tgan hisoblarni yangilash takroran bajarilganda bir xil natija beradi.
- `SystemStateRepository.put()` endi PostgreSQL atomik upsert amalidan foydalanadi; bir xil yangi kalitni parallel yozish asosiy kalit to‘qnashuvini keltirib chiqarmaydi. Lekin `get()` va `put()` ketma-ketligi atomik claim emas: ikkita tick bir vaqtda oldingi qiymatni o‘qib, kunlik ishni takroran boshlashi mumkin. Dars va hisob yozuvlaridagi yagona cheklovlar takroriy qatorlarni saqlashga yo‘l qo‘ymaydi, ammo takroriy ish yoki boshqa yon ta’sirlar ehtimoli qoladi.

### Alohida bajarish uchun taklif

Kunlik claim’ni PostgreSQL’dagi atomik shartli upsert yoki advisory lock bilan himoyalashni alohida PR sifatida taklif qilaman. O‘sha PR’da ikki xil ma’lumotlar bazasi sessiyasidan parallel ishga tushadigan integratsiya testi qo‘shiladi: faqat bitta tick claim olishi va takroriy kunlik ish bajarilmasligi tekshiriladi. Hozirgi o‘zgarish faqat `system_state` kalitini xavfsiz upsert qiladi; scheduler claim oqimini o‘zgartirmaydi.

## Faza 2 uchun “Meni eslab qol” rejasi

Hozirgi imzolangan token serverdan alohida bekor qilinmaydi. Shuning uchun cookie muddatini uzaytirishning o‘zi server tomonda bekor qilish imkonini bermaydi.

| Yondashuv | Afzalligi | Cheklovi |
|---|---|---|
| Serverdagi session jadvali | Bitta qurilma sessiyasini alohida bekor qilish mumkin; “Meni eslab qol” muddati boshqa sessiyalardan mustaqil; `logout` server tomonda darhol bekor qiladi. | Yangi jadval, migratsiya va eskirgan yozuvlarni tozalash kerak; har so‘rovda sessiya holatini tekshirish qo‘shimcha o‘qish talab qiladi. |
| Foydalanuvchi token versiyasi | Foydalanuvchiga bitta versiya maydoni qo‘shiladi; token versiyasi bazadagi qiymatga teng bo‘lmasa rad etiladi; versiyani oshirish barcha sessiyalarni bekor qiladi. | Bitta qurilma sessiyasini alohida bekor qilib bo‘lmaydi; foydalanuvchining barcha sessiyalari birga tugaydi; har so‘rovda versiyani tekshirish kerak. |

**Tavsiya:** serverdagi session jadvalidan foydalanish; cookie’da tasodifiy maxfiy qiymat berish yoki imzolangan token’ga session ID qo‘shish; bazada token xeshi, foydalanuvchi, yaratilgan va tugash vaqti, bekor qilingan holatini saqlash. “Meni eslab qol” uzoqroq amal qiladigan sessiya yaratadi; qisqa va uzoq sessiyalar uchun `HttpOnly`, `Secure`, `SameSite` cookie atributlari saqlanadi. `Logout` joriy sessiyani bekor qiladi. Bazada faqat token xeshi saqlanadi, bekor qilingan va muddati tugagan yozuvlar tozalanadi; foydalanuvchi faqat o‘z sessiyasini bekor qilishi test bilan tekshiriladi. Bu dastlabki reja, hozir kod yoki migratsiya qilinmaydi.
