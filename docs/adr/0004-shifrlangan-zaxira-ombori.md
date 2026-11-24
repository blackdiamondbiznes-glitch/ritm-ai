# ADR 0004: Shifrlangan zaxira ombori

- Holat: tasdiq uchun taklif
- Sana: 2026-11-24

## Kontekst

Hozirgi kunlik `pg_dump` nusxasi Telegram orqali super adminlarga fayl sifatida
yuboriladi. Zaxirada o‘quvchilar, darslar va to‘lovlarga oid shaxsiy ma’lumotlar bo‘lishi
mumkin. Telegram chatini uzoq muddatli zaxira ombori deb qabul qilish xavfli: hisob yoki
qurilmaga kirish, nusxani qayta ulashish va saqlash muddatini boshqarish qiyin.

Zaxira nusxasi ilovadan alohida omborda saqlanishi, yuklashdan oldin shifrlanishi va
tiklash mashqi bilan tekshirilishi kerak. Telegram’ga faqat zaxira muvaffaqiyatli
bajarilgani haqidagi qisqa xabar yuboriladi; nusxaning o‘zi yuborilmaydi.

## Ko‘rib chiqilgan variantlar

Narxlar 2026-11-24 kuni provayderlarning ochiq tarif sahifalarida ko‘rsatilgan saqlash
narxlaridir. Yakuniy hisobga so‘rovlar, soliq, hudud, hajm va saqlash muddati ta’sir
qiladi.

| Variant | Taxminiy xarajat | Murakkablik | Xususiyat va xavf |
|---|---|---|---|
| Cloudflare R2 Standard va mijoz tomonida `age` shifrlashi | 0.015 AQSh dollari/GB-oy; oyiga 10 GB-oy bepul. Internetga chiqarish uchun alohida to‘lov yo‘q. | O‘rta | S3 bilan mos API; yuklash, o‘chirish siyosati va kalitni alohida boshqarish kerak. |
| Backblaze B2 va mijoz tomonida `age` shifrlashi | 6.95 AQSh dollari/TB-oydan; dastlabki 10 GB bepul. Oylik saqlangan hajmning uch baravarigacha chiqish bepul. | O‘rta | S3 bilan mos API va past saqlash narxi; chiqish hajmi chegarasidan oshish xarajatni o‘zgartiradi. |
| Amazon S3 va KMS | Hudud va saqlash sinfiga qarab GB-oy, so‘rov, ma’lumot uzatish hamda KMS amallari uchun haq olinadi. | Yuqori | IAM, KMS, saqlash muddati va tiklash ruxsatlarini sozlash kerak; AWS tajribasi mavjud bo‘lsa boshqarish osonlashadi. |

Narx manbalari: [Cloudflare R2 tariflari](https://developers.cloudflare.com/r2/pricing/),
[Backblaze B2 tariflari](https://www.backblaze.com/cloud-storage/pricing) va
[Amazon S3 tariflari](https://aws.amazon.com/s3/pricing/).

## Tavsiya

Cloudflare R2 Standard’ni alohida zaxira ombori sifatida tanlash taklif qilinadi.
Boshlang‘ich zaxira hajmi kichik bo‘lsa, bepul hajm yetishi mumkin; hajm o‘sganda saqlash
narxi va nusxani tiklashdagi chiqish to‘lovisiz ishlashi qulay. Bu xarajatlarning
kafolati emas: ishga tushirishdan oldin amaldagi tarif va kutilgan hajm qayta hisoblanadi.

`pg_dump` avval vaqtinchalik faylga olinadi, `age` bilan mijoz tomonida shifrlanadi va
shundan keyingina R2’ga yuklanadi. Shifrlash kaliti ombor hisobidan va zaxira faylidan
alohida, maxfiy sozlama sifatida saqlanadi. Kalit yo‘qolsa nusxani tiklab bo‘lmasligi
sababli, tiklash vakolati va favqulodda kalit nusxasini saqlash tartibi alohida belgilanadi.

Telegram faqat muvaffaqiyat yoki xato holatini bildiradi; xabarda ma’lumotlar, ulanish
manzili, parol yoki zaxira fayli bo‘lmaydi. Ombor hisobiga eng kam zarur ruxsat beriladi,
saqlash muddati belgilanadi va CI’dagi tiklash mashqi hamda davriy qo‘lda tiklash bilan
nazorat qilinadi.

## Oqibatlar va keyingi qarorlar

- Ushbu ADR faqat taklif; hozirgi Telegram zaxira oqimi o‘zgartirilmaydi.
- Amalga oshirishdan oldin ombor hisobini kim boshqarishi, shifrlash kalitini qanday
  tiklash va nusxalarni qancha muddat saqlash belgilanadi.
- Alohida PR’da zaxirani shifrlash, omborga yuklash, xatolarni xabar qilish va vaqtinchalik
  ochiq fayllarni xavfsiz tozalash qo‘shiladi.
- Telegram’dagi avvalgi nusxalar avtomatik o‘chirilmaydi; ularni saqlash yoki olib tashlash
  bo‘yicha amaliy qaror alohida qabul qilinadi.
