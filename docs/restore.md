# Zaxira nusxasidan tiklash

Bu yo‘riqnoma PostgreSQL’ning `pg_dump` custom formatidagi nusxasini yangi, bo‘sh
bazaga tiklash uchun. Ishlab turgan yoki ichida ma’lumot bor bazaga tiklamang.

## Zaxira nusxasi qayerda

Ilova har kuni Toshkent vaqti bilan 04:00 da, `SUPER_ADMIN_IDS` ro‘yxatidagi Telegram
hisoblariga ma’lumotlar bazasi nusxasini hujjat sifatida yuborishga urinadi. Xizmat uxlab
qolsa, rejalashtirilgan ish o‘tmay qolishi mumkin; kunlik yetkazib berish kafolatlanmaydi.
Nusxa vaqtinchalik faylga olinadi va yuborish urinishidan keyin o‘chiriladi; bot
tiklanadigan nusxani o‘zida saqlamaydi. `BACKUP_MAX_MB` chegarasidan katta nusxa yuborilmaydi.

Telegram chatidagi nusxa ilova darajasida shifrlanmaydi. Unda o‘quvchilarning shaxsiy
ma’lumotlari, dars va to‘lov yozuvlari bo‘lishi mumkin. Chat yoki admin hisobiga kirish,
faylni boshqa joyga uzatish va qurilmada saqlanish xavflarini hisobga oling. Telegram’ni
yagona, uzoq muddatli zaxira ombori deb qabul qilmang. Tavsiya: nusxalarni mijoz tomonda
shifrlab, alohida boshqariladigan kalit va cheklangan ruxsatli obyekt omborida saqlash,
saqlash muddatini belgilash va tiklashni muntazam sinash. Bu shifrlangan ombor ushbu
o‘zgarishda joriy qilinmaydi.

## Tiklash tartibi

1. Telegram’dagi kerakli kun nusxasini ishonchli, vaqtinchalik ish muhitiga yuklab oling.
   Faylni chatdan tashqariga uzatmang va umumiy katalogga qo‘ymang.
2. PostgreSQL’da alohida, bo‘sh maqsad baza yarating. Imkon bo‘lsa, avval lokal yoki
   sinov muhitida tiklab, ilova tekshiruvlarini bajaring.
3. Maxfiy ulanish manzilini terminalda ko‘rinmaydigan qilib kiriting. URL’ni buyruq
   qatoriga, repozitoriyga yoki jurnalga yozmang:

   ```sh
   read -rsp 'Tiklash bazasining PostgreSQL manzili: ' RESTORE_DATABASE_URL
   export RESTORE_DATABASE_URL
   printf '\n'
   ```

4. Repozitoriy ildizida skriptni ishga tushiring. `--confirm-empty-target` majburiy;
   skript arxivni tekshiradi, bazada obyektlar yo‘qligini tasdiqlaydi va keyin tiklaydi:

   ```sh
   python -m scripts.restore_db /xavfsiz/yo‘l/ritm-YYYYMMDD.dump --confirm-empty-target
   unset RESTORE_DATABASE_URL
   ```

5. Skript `psql` va `pg_restore` talab qiladi. U ulanish manzilini yoki parolni
   buyruq argumentlarida uzatmaydi. `--clean` ishlatilmaydi; tiklash bitta tranzaksiyada
   bajariladi, xato bo‘lsa tranzaksiya qaytariladi. Bo‘sh bo‘lmagan baza aniqlansa,
   tiklash boshlanmaydi.
6. Tiklangan bazani sinovdan o‘tkazing: migratsiya holati, kerakli jadvallar, foydalanuvchi
   va o‘qituvchi yozuvlari, bot hamda Mini App’ning asosiy oqimlari. Ilova kodidan eskiroq
   nusxa bo‘lsa, tekshirilgan muhitda mos migratsiyalarni qo‘llang.
7. Faqat natija tasdiqlangach, hosting sozlamalaridagi `DATABASE_URL`ni yangi ulanishga
   o‘zgartiring va ilovani qayta ishga tushiring. Eski bazani o‘chirishdan avval yangi
   ulanish bilan ish holatini tasdiqlang. Tiklashni bevosita ishlab turgan bazaga
   yo‘naltirmang.
8. Vaqtinchalik nusxa va ulanish manzilini xavfsiz tozalang. Tiklash muvaffaqiyatli
   tugagach, ishlatilgan faylni himoyalangan saqlash tartibiga muvofiq olib tashlang.
