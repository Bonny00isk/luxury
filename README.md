# 🎴 Anime Cards Bot

Telegram-бот для коллекционирования аниме-карточек с Mini App.

## Установка

```bash
git clone https://github.com/Bonny00isk/luxury
cd luxury

python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows

pip install -r requirements.txt

# Настройка
cp .env.example .env
# Открой .env и заполни:
# BOT_TOKEN — НОВЫЙ токен от @BotFather
# ADMIN_ID — Telegram ID владельца админ-панели
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

В Render добавь переменные окружения `BOT_TOKEN`, `ADMIN_ID` и `WEBAPP_URL`.
Локально их можно хранить в файле `.env`; этот файл не должен попадать в Git.

Веб-админка открывается командой `/admin` в личном чате с ботом. Доступ
проверяется сервером по подписи Telegram Mini App `initData`; ключи и токены
не передаются в URL или frontend-код.

Не добавляй реальные секреты в репозиторий. Если токен бота публиковался,
отзови его через @BotFather и установи новый в переменных окружения.
