# Referal konkurs bot (Telegram)

Majburiy obuna + referal + random qozon + avtomatik g'olib aniqlash + to'liq admin panel.

## Qanday ishlaydi

1. Foydalanuvchi botga kiradi va **majburiy kanallarga obuna bo'ladi** (✅ Tekshirish tugmasi).
2. «🔗 Taklif havolam» orqali shaxsiy havolasini oladi: `https://t.me/<bot>?start=<user_id>`.
3. Do'sti shu havola orqali botga **birinchi marta** kirib, barcha kanallarga obuna bo'lgandagina
   taklif **tasdiqlanadi** (soxta takliflarning oldi olinadi). Taklif qiluvchiga xabar boradi.
4. **N ta** tasdiqlangan do'st taklif qilgan foydalanuvchi avtomatik ravishda **random qozonga** qo'shiladi.
5. Belgilangan **sana va vaqtda** bot qozondan `random.SystemRandom` yordamida **n ta g'olibni** tanlaydi
   (ixtiyoriy: tanlashda g'olibning hali ham kanallarda ekanligi qayta tekshiriladi).
6. G'oliblarga, adminlarga va (ixtiyoriy) barcha foydalanuvchilarga natija e'lon qilinadi.

## Foydalanuvchi menyusi

| Tugma | Vazifasi |
|---|---|
| 🔗 Taklif havolam | Shaxsiy havola + «Do'stlarga ulashish» tugmasi |
| 📊 Mening natijam | Tasdiqlangan takliflar soni, qozondami yoki yo'q |
| 🏆 Reyting | TOP-10 taklif qiluvchilar |
| ℹ️ Konkurs haqida | Shartlar, sovg'alar, sana |
| 🎁 G'oliblar | Aniqlangan g'oliblar ro'yxati |

## Admin panel (`/admin` yoki «⚙️ Admin panel»)

- **📊 Statistika** — foydalanuvchilar, bloklaganlar, bugungi yangi, takliflar, qozon hajmi.
- **📢 E'lon yuborish** — istalgan turdagi xabar (matn, rasm, video, fayl, ovoz, so'rovnoma...),
  ostiga **har xil tugmalar** qo'shish, oldindan ko'rish va tasdiqlash. Yuborish fon rejimida, ~25 xabar/s,
  botni bloklaganlar avtomatik belgilanadi.

  Tugmalar formati (har qator — klaviatura qatori, bir qatordagi tugmalar `|` bilan):
  ```
  Kanalimiz - https://t.me/kanal | Sayt - https://site.uz
  Kanal - @kanal_username
  Ilova - webapp:https://site.uz
  Ulashish - share:Zo'r bot ekan!
  Do'stlarni taklif qilish - ref      ← har bir foydalanuvchiga o'zining taklif havolasi
  Botga o'tish - bot
  Shartlar - alert:3 ta do'st taklif qiling   ← bosilganda oyna chiqadi
  ```
- **🎯 Konkurs** — boshlash/to'xtatish, takliflar soni (N), g'oliblar soni, sana, sovg'a matni,
  qozon ro'yxatini CSV yuklab olish, g'oliblarni hozir aniqlash, yangi konkurs boshlash (hisoblar 0 dan).
- **📡 Majburiy kanallar** — qo'shish (`@username`, `-100...` ID, yoki forward), o'chirish.
  Yopiq kanal uchun: `-1001234567890 https://t.me/+AbCdEf`. Bot kanalda **admin** bo'lishi shart.
- **⚙️ Bot sozlamalari** — botni yoqish/o'chirish (texnik ishlar), g'olib tanlashda obunani qayta tekshirish,
  natijani hammaga e'lon qilish, start xabarini tahrirlash (`{name}` — foydalanuvchi ismi).
- **👮 Adminlar** — qo'shimcha adminlar qo'shish/o'chirish (faqat `.env` dagi asosiy adminlar).

## O'rnatish

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # BOT_TOKEN va ADMIN_IDS ni to'ldiring
python -m bot
```

Docker bilan:

```bash
docker build -t referal-bot .
docker run -d --env-file .env -v $(pwd)/data:/app/data --name referal-bot referal-bot
```

### Ishga tushirgandan keyin

1. Botni majburiy kanallarga admin qiling va admin paneldan kanallarni qo'shing.
2. 🎯 Konkurs → N, g'oliblar soni, sana va sovg'a matnini belgilang → **▶️ Boshlash**.

## Arxitektura

```
bot/
├── __main__.py            # ishga tushirish, dispatcher, rejalashtiruvchi
├── config.py              # .env sozlamalari
├── db.py                  # SQLite (aiosqlite): users, referrals, winners, channels, admins, settings, alerts
├── keyboards.py           # klaviaturalar
├── middlewares.py         # ro'yxatga olish + referal, bot holati, majburiy obuna
├── services/
│   ├── subscription.py    # obunani tekshirish (60 s kesh)
│   ├── contest.py         # taklifni tasdiqlash, random qozon, g'olib aniqlash, scheduler
│   ├── broadcast.py       # ommaviy xabar yuborish (rate-limit, RetryAfter, blok)
│   └── buttons.py         # e'lon tugmalarini parse qilish
└── handlers/
    ├── user.py            # foydalanuvchi menyusi
    └── admin/             # panel, broadcast, channels, contest, settings (+ adminlar)
```

- **Random qozon** alohida jadvalda saqlanmaydi — u `referrals` jadvalidan dinamik hisoblanadi
  (`COUNT(confirmed) >= N`). Shuning uchun N o'zgartirilsa, qozon darhol yangilanadi.
- Har bir foydalanuvchi faqat bir marta taklif qilingan bo'lishi mumkin (`referred_id` — PRIMARY KEY),
  o'zini o'zi taklif qilish mumkin emas.
- «Yangi konkurs» `contest_id` ni oshiradi — eski takliflar va g'oliblar arxivda qoladi.
- Rejalashtiruvchi har 20 soniyada sanani tekshiradi; bot qayta ishga tushsa ham sana bazada saqlanadi.
- G'olib tanlash `asyncio.Lock` bilan himoyalangan — ikki marta o'tkazilmaydi.
