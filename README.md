# 🎴 Anime Cards Bot

Telegram-бот для коллекционирования аниме-карточек с Mini App.

## Установка

```bash
git clone https://github.com/GamerMax1254/anime-cards-bot
cd anime-cards-bot

python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

pip install -r requirements.txt

# Настройка
cp .env.example .env
# Открой .env и заполни:
# BOT_TOKEN — НОВЫЙ токен от @BotFather
# ADMIN_ID=7694677506
# ADMIN_KEY — длинный случайный секретный ключ
# WEBAPP_URL — публичный HTTPS-адрес Mini App

# Запуск ngrok (в отдельном терминале)
ngrok http 127.0.0.1:8080

# Запуск бота
python run.py
```

## Возможности

- 🎰 Гача-система с 8 редкостями
- 💰 Экономика с ежедневными наградами
- 🎴 Коллекция и альбом персонажей
- 👑 Веб-админка
- 💡 Система предложений от пользователей
- 🖼 Загрузка картинок

## Технологии

- Python 3.9+
- Aiogram 3.x
- FastAPI
- SQLAlchemy
- Telegram Mini App


## Настройки доступа

Владелец админ-панели: Telegram ID `7694677506`.
Открывай панель командой `/admin` в личном чате с ботом. Секретный `ADMIN_KEY`
передаётся в ссылке админ-панели; не пересылай эту ссылку другим людям.

Секреты хранятся в `.env`, который исключён из Git. Не добавляй `.env` в репозиторий.
Если токен бота когда-либо публиковался или отправлялся в общий чат, отзови его
через @BotFather и используй новый.
