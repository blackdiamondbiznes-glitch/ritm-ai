# ADR 0002: Foydalanuvchi uchun asosiy yuza

- Holat: qabul qilindi
- Sana: 2026-11-24

## Kontekst

O‘qituvchilar ko‘pincha kompyuter yoki planshetda guruh, jadval, o‘quvchi, davomat va to‘lovlarni boshqaradi. O‘quvchilar esa Telegram bot va Mini App’dan foydalanadi. O‘qituvchining mobil kabineti kerak bo‘lib qolishi mumkin, ammo asosiy ish joyi bo‘lishi shart emas.

## Qaror

- O‘qituvchi uchun asosiy ish joyi `/panel` veb-panel hisoblanadi.
- O‘qituvchiga qo‘shiladigan yangi boshqaruv funksiyasi avval panelda chiqariladi.
- O‘qituvchining Mini App kabineti o‘chirilmaydi; telefonda zaxira yuza sifatida saqlanadi.
- O‘quvchining asosiy yuzasi o‘zgarmaydi: Telegram bot va Mini App.
- Panel desktop va planshetga moslanadi; asosiy amallar klaviatura bilan bajariladi, bosish nishonlari kamida 44 px bo‘ladi.

## Oqibatlar

- Yangi o‘qituvchi funksiyalarida panel uchun mos amallar, bo‘sh holat, yuklanish va xato holatlari, shuningdek, uch tildagi matnlar bo‘lishi kerak.
- Mini App’dagi mavjud o‘qituvchi amallari zaruratda zaxira yuza sifatida saqlanadi; ularni parallel takomillashtirish alohida hal qilinadi.
- Yangi imkoniyatni faqat telefon kabinetida chiqarish mumkin emas; avval panelda chiqarish kerak.
