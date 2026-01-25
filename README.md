# Telegram Test Bot — Production (Uzbek)

Bu loyiha Telegram orqali:
- Test PDF tarqatish
- Testni Telegram ichida tugmalar bilan tekshirish
- SAT va Milliy Sertifikat uchun **Rasch (1PL IRT)** asosida nisbiy baholash (baseline 10 ta)
- Sertifikat PDF generatsiya qilish

## 1) Talablar
- Python 3.11+ (tavsiya: 3.12)
- (Ixtiyoriy) PostgreSQL emas, bu build **SQLite** bilan ishlaydi (data/bot.db)

## 2) O‘rnatish (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

## 3) Sozlash
`.env` faylini yarating (namuna: `.env.example`):

- `BOT_TOKEN` — bot token
- `ADMIN_TG_IDS` — admin telegram ID lar (vergul bilan)
- `REQUIRED_CHANNEL` — majburiy kanal (`@kanal` yoki `https://t.me/...`)
- `REQUIRED_GROUP` — majburiy guruh (`@guruh` yoki `https://t.me/...`)

## 4) Ishga tushirish
```powershell
py -m app.main
```

Bot birinchi ishga tushganda DB jadvalarini yaratadi.

### Migratsiya (majburiy)
Milliy Sertifikat uchun **multi-answer + manual** javoblar qo'shilgani uchun `correct_answer` maydoni kengaytirildi.
Bir marta quyidagini bajaring:

```powershell
py -m alembic upgrade head
```

## 5) Foydalanuvchi oqimi (UZ)
- `/start` → kanal+guruh a’zolik tekshiruvi (bot ham, Mini App ham tekshiradi)
- Asosiy menyu:
  - **📝 Test ishlash (Mini App)** — javoblarni kiritish Mini App’da
  - **📄 Test PDF olish** — PDF bot chatiga yuboriladi
  - **📞 Telefon raqamni ulashish** — CEO hisobotiga tushadi
  - **🧹 Clear**
- Har ikkala oqimda 5 kategoriya:
  1) Milliy Sertifikat tayyorlov
  2) SAT tayyorlov
  3) DTM tayyorlov
  4) Prezident maktabiga tayyorlov
  5) Mavzulashtirilgan testlar

## 6) Admin panel (Telegram ichida)
Admin botga: `/admin`

Tugmalar:
- ➕ Yangi test yaratish
- ♻️ Testni yangilash (PDF/Javob)
- 🗑 Testni o‘chirish
- 📊 Rasch bazasi (10 ta)

### 6.1 Rasch bazasi (MUHIM)
SAT va Milliy testlar Rasch hisoblanadi.
Har bir Rasch test uchun **aniq 10 ta baseline** (soxta foydalanuvchi) javoblari kiritilishi shart.
Aks holda foydalanuvchi “Test tekshirish”ni boshlay olmaydi.

Baseline userlar DB da tg_id = -1..-10 sifatida saqlanadi.

## 7) Sertifikatlar
- Oddiy testlar (DTM/Prezident/Mavzu): foiz bo‘yicha sertifikat
- SAT: “Math Score (200–800)” ko‘rinishida
- Milliy: foiz + daraja (C, C+, B, B+, A, A+) qoidalari bilan

## 8) Papkalar
- `data/tests/` — admin yuklagan PDF testlar
- `data/certificates/` — generatsiya qilingan sertifikatlar
- `data/bot.db` — SQLite bazasi

## 9) Xavfsizlik eslatmalari
- `ADMIN_TG_IDS` ni faqat ishonchli adminlarga bering.
- REQUIRED_CHANNEL / REQUIRED_GROUP ni to‘g‘ri sozlang.

---
Muallif: Sizning talabingiz bo‘yicha, to‘liq Telegram UX bilan.

## 10) Rollar (User/Admin/CEO)
- `ADMIN_TG_IDS` va `CEO_TG_IDS` **ko‘p ID** qabul qiladi.
- Bitta foydalanuvchi **Admin ham, CEO ham** bo‘lishi mumkin.
- Bunday holatda foydalanuvchi asosiy menyuda **ikkala panel**ni ham ko‘radi va ruxsatlar birlashadi.

CEO panel:
- **Userlar ro'yxatini olish (pdf)** — barcha userlar (tg_id, username, telefon, qo‘shilgan vaqt) bo‘yicha PDF hisobot.

Sertifikat:
- Test yakunida Mini App natija sahifasida **"Sertifikatni botga yuborish"** tugmasi bor — bosilganda sertifikat PDF bot chatiga yuboriladi.
