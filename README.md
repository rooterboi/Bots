# Multi-Bot Maker (aiogram 3 + yt-dlp + FFmpeg + SQLite)

Maker bot → foydalanuvchi token kiritib **Kino/Serial** yoki **Musiqa/Media** sub-bot yaratadi. Barcha botlar bitta jarayonda (polling) ishlaydi.

## Ishga tushirish
1. `.env.example` → `.env` (MAKER_BOT_TOKEN, OWNER_ID). Lokal: `pip install -r requirements.txt`, FFmpeg o'rnatilgan bo'lsin, `python main.py`.
2. GitHub'ga yuklang → Render → New Web Service (Docker; `render.yaml` bor). Env: `MAKER_BOT_TOKEN`, `OWNER_ID`.

## Muhim eslatmalar
- **Render free diskida SQLite saqlanmaydi** (restart/deploy'da baza o'chadi) va servis 15 daqiqa so'rovsiz uxlaydi: `/` manzilini UptimeRobot bilan pinglang. Doimiy baza uchun pullik disk (`DB_PATH` ni disk ichiga) kerak.
- Rejim: **polling** (webhook yo'q). Sub-bot ma'lumotlari bitta bazada `bot_id` ustuni bilan ajratilgan.
- "💳 to'lov" avtomatik emas: balans promokod, referal yoki admin (ID bo'yicha) orqali to'ldiriladi.
- Telegram Bot API fayl limiti: yuklash 50 MB, `/cut` uchun yuklab olish 20 MB.
- TikTok/Instagram yuklash yt-dlp'ga bog'liq (platforma o'zgarsa yt-dlp'ni yangilang: `pip install -U yt-dlp`). Watermarksiz format yt-dlp tomonidan imkon bo'lsa tanlanadi.
- "🆓 Faqat Oddiy" toifasi: Premium tizimi yoqilganda faqat Premium bo'lmaganlarga ko'rinadi.
- Kod aiogram'siz muhitda sintaksis jihatdan tekshirilgan; birinchi ishga tushirishda sinab ko'ring.

## Yangi (v2)
- **💳 Karta orqali to'lov**: Maker va har bir sub-botda `/admin → 💳 To'lov sozlamalari` — karta raqami, egasi, minimal summa, yoqish/o'chirish. Foydalanuvchi «➕ To'ldirish» → summa → chek rasmi → adminlarga tugmali xabar (✅ Tasdiqlash / ❌ Rad etish). Tasdiqlansa balans avtomatik to'ldiriladi. (Pul o'tkazmasini admin kartasidan o'zi tekshiradi — avtomatik Click/Payme emas.)
- **Yangi bot turlari**: 📩 Murojaat (Support) boti, 🎁 Konkurs (Referal reyting) boti.
