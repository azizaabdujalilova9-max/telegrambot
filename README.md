# Telegram test bot

Telegram test bot aiogram 3 va SQLite yordamida ishlaydi. Bot foydalanuvchiga test va savollar sonini tanlash, savol/variantlarni aralashtirish hamda har bir javobdan keyin natijani ko'rsatish imkonini beradi. Admin JSON fayllardan test qo'shishi va testlarni o'chirishi mumkin.

## O'rnatish va ishga tushirish
ADMIN_ID : 7868728106
1. Python 3.10 yoki undan yangisini o'rnating.
2. Virtual muhit yarating va yoqing:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Bog'liqliklarni o'rnating:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. `.env.example` faylidan nusxa olib `.env` yarating. `BOT_TOKEN` va `ADMIN_ID` qiymatlarini kiriting.
   - `BOT_TOKEN` ni Telegram'dagi [@BotFather](https://t.me/BotFather) orqali oling.
   - `ADMIN_ID` — admin Telegram akkauntining raqamli user ID si.
5. Botni ishga tushiring:

   ```powershell
   python bot.py
   ```

Ma'lumotlar standart holatda `quiz_bot.sqlite3` faylida saqlanadi. Boshqa manzil kerak bo'lsa, `.env` ichida `DATABASE_PATH` ni o'zgartiring.

## Admin

- `/admin` buyrug'ini yuboring yoki admin hisobidan **Admin panel** tugmasini bosing.
- Test qo'shish uchun `.json` faylni botga yuboring. Fayl nomi `.json` bilan tugashi va JSON UTF-8 formatida bo'lishi kerak.
- **Testlarni boshqarish** bo'limida testni tanlab, o'chirishni tasdiqlang.

## JSON formati

`json_example/test_example.json` tayyor namunadir. `answer` qiymati `options` ro'yxatidagi **1 dan boshlanadigan** to'g'ri variant raqami:

```json
{
  "title": "Test nomi",
  "description": "Ixtiyoriy izoh",
  "questions": [
    {
      "question": "Savol matni",
      "options": ["Birinchi variant", "Ikkinchi variant"],
      "answer": 2
    }
  ]
}
```

Har bir savolda kamida ikkita bo'sh bo'lmagan variant bo'lishi kerak. Savollar va variantlar har bir urinishda tasodifiy tartibda beriladi. Foydalanuvchi javob bergach, bot javob to'g'ri yoki noto'g'riligini ko'rsatadi va yakunda natijani bazaga yozadi.
