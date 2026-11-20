# run.py
import asyncio
import threading
import uvicorn
from database import init_db
from seed import seed_if_empty
from config import SERVER_HOST, SERVER_PORT, BOT_TOKEN, ADMIN_KEY


def start_server():
    uvicorn.run(
        "server:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        log_level="info",
    )


async def start_bot():
    from bot import dp, bot
    if not BOT_TOKEN:
        print("❌ Не задан BOT_TOKEN. Заполни .env.")
        return
    if not ADMIN_KEY:
        print("❌ Не задан ADMIN_KEY. Заполни .env.")
        return
    print("🤖 Бот запускается...")
    try:
        me = await bot.get_me()
        print(f"✅ Бот подключён: @{me.username} ({me.first_name})")
    except Exception as e:
        print(f"❌ ОШИБКА ПОДКЛЮЧЕНИЯ К БОТУ: {e}")
        print("   Проверь BOT_TOKEN в .env!")
        return

    await dp.start_polling(bot)


def main():
    print("=" * 50)
    print("🚀 Запуск Anime Cards Bot")
    print("=" * 50)

    # 1. БД
    init_db()
    seed_if_empty()

    # 2. Сервер
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    print(f"🌐 Сервер: http://localhost:{SERVER_PORT}")

    # 3. Бот
    asyncio.run(start_bot())


if __name__ == "__main__":
    main()