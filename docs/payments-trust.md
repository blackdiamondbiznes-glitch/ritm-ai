# To'lovlar: ishonch va nizolardan himoya

Bu hujjat Ritm AI'da qo'lda (karta orqali) qabul qilinadigan to'lovlar qanday himoyalanganini, qaysi xavflar hali ham qolganini va avtomatik tekshiruvga (Click / Payme / Uzum) qanday o'tishni tushuntiradi.

> Hujjatdagi karta raqamlari namuna. Haqiqiy raqamlar faqat serverdagi `.env` faylida turadi (`PAYMENT_CARD_*`, `PAYMENT_CARD2_*`).

## 1. Qaysi nizolardan himoya qilamiz

| Xavf | Misol | Himoya |
|---|---|---|
| Mijoz to'lagan, lekin admin "pul kelmadi" deydi | Admin xato qiladi yoki to'lovni topolmaydi | Har so'rovda noyob kod va noyob summa, majburiy chek, karta oxirgi 4 raqami va o'tkazma vaqti. Har bir qadam o'zgarmas jurnalga yoziladi. Rad etilsa, sabab majburiy va mijoz bir marta e'tiroz bildira oladi |
| Mijoz soxta yoki eski chek yuboradi | Boshqa odamning chekini yoki tahrirlangan rasmni yuboradi | Chekning Telegram `file_unique_id` qiymati saqlanadi; bir chek ikkinchi marta ishlatilsa, adminga "♻️ takroriy chek" deb ko'rsatiladi. Admin "🚩 Soxta chek" tugmasini bosadi; takrorlansa, mijoz to'lovdan bloklanadi |
| Mijoz "men shartlarga rozilik bermaganman" deydi | Pul qaytarishni talab qiladi | Oferta tugma bilan qabul qilinadi; versiyasi va vaqti so'rovga yoziladi |
| Mijoz "pul yubordim, tarif yoqilmadi" deydi | Tasdiqdan keyin nizo | Tasdiqlanganda mijozga kvitansiya xabari boradi: kod, summa, tarif, muddat, sana |
| Ikki mijoz bir xil summani bir vaqtda o'tkazadi | Qaysi pul kimniki ekani noaniq | Summaga 1–99 so'm qo'shiladi; ochiq so'rovlar orasida bir xil summa takrorlanmaydi |

## 2. Mijoz uchun jarayon

1. **💳 Tarif va obuna → 💳 To'lov**: tarif va muddat tanlanadi.
2. **Oferta** ekrani: 7 banddan iborat shartlar. "✅ Shartlarni qabul qilaman" bosilmaguncha karta ko'rsatilmaydi.
3. **Hisob-faktura**: masalan `RITM-7KQ2` kodi, `99 047 so'm` aniq summa va kartalar:
   - Uzcard `8600 0000 0000 0000`, egasi: Ism Familiya
   - Visa `4000 0000 0000 0000`, egasi: Ism Familiya

   Raqamlar to'rttadan guruhlangan va bosilganda nusxalanadi. Mijozdan aynan shu summani o'tkazish va izohga kodni yozish so'raladi.
4. Pul o'tkazilgach, **"✅ To'lov qildim"** bosiladi.
5. Bot ketma-ket so'raydi:
   - to'lagan kartaning oxirgi 4 raqami;
   - o'tkazma vaqti (`14:35`, `20.11 14:35` yoki "🕐 Hozirgina" tugmasi);
   - chek: skrinshot, rasm yoki PDF. Chek **majburiy**, chek yuborilmasa so'rov adminga bormaydi.
6. Mijozga tasdiq xabari keladi: kod, summa, karta oxiri, vaqt va "12 soat ichida tekshiriladi".
7. Natija:
   - **Tasdiqlandi**: kvitansiya xabari keladi va tarif darhol yoqiladi.
   - **Rad etildi**: sabab ko'rsatiladi va "⚖️ E'tiroz bildirish" tugmasi chiqadi. Mijoz bir marta matnli e'tiroz yozadi; so'rov "E'tiroz" holatiga o'tadi va barcha adminlarga to'liq tarix bilan qayta yuboriladi.
   - **Soxta chek**: mijoz ogohlantiriladi. `PAYMENT_FAKE_BLOCK_AFTER` (standart 2) marta takrorlansa, to'lov qilish bloklanadi. Blokni faqat super admin sabab yozib olib tashlaydi.

Chek yuborilmagan so'rov (qoralama) `PAYMENT_DRAFT_TTL_HOURS` (standart 24 soat) o'tgach avtomatik bekor bo'ladi. Chek yuborilgan so'rov hech qachon o'z-o'zidan yopilmaydi; uni faqat admin yopadi.

## 3. Admin uchun jarayon

Botdagi **💰 To'lovlar** yoki Mini ilovadagi **🛡️ Admin → To'lovlar** bo'limi ishlatiladi. Ikkalasi bitta servisdan foydalanadi, shuning uchun qoidalar va jurnal bir xil; jurnalda `via` maydoni `bot` yoki `webapp` bo'ladi.

- Har bir so'rovda quyidagilar ko'rinadi: kod, aniq summa, tarif narxi, karta oxiri, o'tkazma vaqti, oferta versiyasi, chek rasmi yoki PDF, takroriy chek va oldingi soxta cheklar haqidagi ogohlantirishlar, hamda hodisalar tarixi.
- **Tasdiqlashdan oldin** bank ilovasida aynan shu summa va vaqt bo'yicha tushum borligini tekshiring. Summa noyob bo'lgani uchun uni qidirish oson.
- **Rad etish** faqat sabab bilan: tayyor sabablardan birini tanlash yoki o'zingiz yozish mumkin.
- **Soxta chek** belgisi rad etish bilan bir xil ishlaydi, qo'shimcha ravishda mijoz hisobiga qayd qo'shadi.
- Mini ilovadagi Admin panelda yana quyidagilar bor:
  - mijozlar ro'yxati va qidiruv;
  - tarif berish va muddatni uzaytirish (sabab majburiy, auditga yoziladi);
  - to'lovni bloklash va blokdan chiqarish;
  - chatlar ro'yxati;
  - umumiy ko'rsatkichlar;
  - audit jurnali.
- Chek rasmi Telegram serveridan bot orqali olinadi. Telegram havolasi brauzerga berilmaydi; endpoint faqat super adminlarga ochiq.

## 4. Jurnal va dalillar

- `payment_events` jadvali har bir holat o'zgarishini yozadi: kim, qachon, qaysi holatdan qaysiga, sabab, chek ID.
- `audit_logs` jadvaliga tarif berish, uzaytirish va bloklash yoziladi.
- Ikkala jadvalga faqat yozish mumkin. Postgres trigger'i `UPDATE` va `DELETE` buyruqlarini rad etadi, hatto ma'lumotlar bazasiga to'liq kirgan dastur ham yozuvni o'zgartira olmaydi.
- Nizo bo'lsa, admin panelda so'rov tarixini ochib, sanalar va chek bilan birga mijozga ko'rsatish mumkin.

## 5. Qolgan xavflar (halol baho)

1. **Bank bilan avtomatik solishtirish yo'q.** Pul kelganini admin bank ilovasidan o'zi tekshiradi. Odamiy xato hali ham mumkin, lekin noyob summa va kod bu xatoni ancha kamaytiradi.
2. **Tahrirlangan chekni avtomatik aniqlab bo'lmaydi.** Faqat aynan bir xil faylning qayta yuborilishi (`file_unique_id`) aniqlanadi. Qayta saqlangan yoki qirqilgan rasm boshqa fayl hisoblanadi. Chek faqat qo'shimcha dalil; asosiy dalil kartaga tushgan pul.
3. **Karta egasining ismi** mijozga ko'rinadi, bu P2P o'tkazmalar uchun odatiy hol.
4. **Pulni qaytarish (refund)** qo'lda bajariladi va jurnalga avtomatik yozilmaydi. Qaytarilgan bo'lsa, sababini tarifni o'zgartirish izohiga yozing.
5. **Chargeback.** Mijoz bankka murojaat qilsa, karta-kartaga o'tkazmada bank odatda o'tkazma tasdig'ini so'raydi. Jurnal, oferta qabul qilingan vaqt va kvitansiya xabari bunda dalil bo'ladi.

## 6. Kelajak: avtomatik tasdiqlash (Click / Payme / Uzum)

To'lovlar soni oshganda qo'lda tekshirish o'rniga to'lov tizimi ulanadi:

1. Click, Payme yoki Uzum Bank'da merchant shartnomasi tuziladi (YaTT yoki MChJ kerak).
2. Bot to'lov havolasini yaratadi. Hozirgi `RITM-XXXX` kodi va so'rov ID'si merchant tranzaksiyasiga `order_id` sifatida beriladi.
3. To'lov tizimi serverga webhook yuboradi (Payme: `CheckPerformTransaction` / `PerformTransaction`; Click: `prepare` / `complete`). Server imzoni tekshiradi va xuddi shu `PaymentService.approve` funksiyasini `actor_kind="system"`, `via="click"` qiymatlari bilan chaqiradi. Shu sababli jurnal, kvitansiya va tarif yoqilishi o'zgarmaydi.
4. Karta orqali qo'lda to'lash zaxira yo'l sifatida qoladi.
5. Natija: chek, karta oxiri va vaqt kerak bo'lmaydi; to'lov soniyalar ichida tasdiqlanadi; soxta chek xavfi butunlay yo'qoladi.

Kerakli ishlar: merchant kalitlarini `.env`ga qo'shish, webhook endpoint (`/api/pay/<provider>`), imzo tekshiruvi va idempotentlik testlari. Ma'lumotlar bazasidagi `payments` va `payment_events` tuzilmasi bunga allaqachon tayyor.
