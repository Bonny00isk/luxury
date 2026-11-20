# bot.py
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineKeyboardButton, WebAppInfo, MenuButtonWebApp, BotCommand,
    InputMediaPhoto, InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import BOT_TOKEN, WEBAPP_URL, ADMIN_ID, DROP_INTERVAL_HOURS
from database import get_session, GroupChat, Drop
from gacha import GachaService

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
BOT_LOOP = None


def submit_bot_notification(coro):
    """Безопасно отправляет coroutine из потока FastAPI в event loop бота."""
    loop = BOT_LOOP
    if loop is None or not loop.is_running():
        coro.close()
        return False
    asyncio.run_coroutine_threadsafe(coro, loop)
    return True

# Подключаем админку только если файл есть
try:
    from admin import admin_router
    dp.include_router(admin_router)
    print("✅ Админ-роутер подключён")
except ImportError as e:
    print(f"⚠️ Админка не загружена: {e}")
except Exception as e:
    print(f"⚠️ Ошибка админки: {e}")


@dp.message.outer_middleware()
async def track_group_chat_middleware(handler, event: types.Message, data: dict):
    """Регистрирует групповой чат при первом же сообщении в нём — чтобы шедулер дропов его увидел."""
    if event.chat.type in ("group", "supergroup"):
        db = get_session()
        try:
            exists = db.query(GroupChat).filter(GroupChat.chat_id == event.chat.id).first()
            if not exists:
                db.add(GroupChat(
                    chat_id=event.chat.id,
                    title=event.chat.title,
                    last_drop_at=datetime.utcnow(),
                ))
                db.commit()
        finally:
            db.close()
    return await handler(event, data)


@dp.callback_query(F.data.startswith("coll_page_"))
async def coll_page_callback(callback: types.CallbackQuery):
    """Обратная совместимость - переход на страницу"""
    try:
        page = int(callback.data.split("_")[-1])
    except:
        page = 1
    await show_collection_page(callback, page=page, edit=True)
    await callback.answer()


@dp.callback_query(F.data.startswith("view_card_"))
async def view_card_callback(callback: types.CallbackQuery):
    """Показать детали карточки"""
    try:
        card_id = int(callback.data.split("_")[-1])
    except:
        await callback.answer("❌ Ошибка ID")
        return

    db = get_session()
    try:
        from database import Character, User, UserCard
        from sqlalchemy.orm import joinedload

        char = db.query(Character).options(
            joinedload(Character.anime)
        ).filter(Character.id == card_id).first()

        if not char:
            await callback.answer("❌ Карточка не найдена", show_alert=True)
            return

        char_data = {
            "id": char.id,
            "name": char.display_name,
            "name_en": char.name_en,
            "name_jp": char.name_jp,
            "anime_title": char.anime_title,
            "rarity": char.rarity,
            "rarity_info": char.rarity_info,
            "image_url": char.image_url,
            "images": [i.url for i in char.images] or ([char.image_url] if char.image_url else []),
            "description": char.description,
            "power": char.power,
            "defense": char.defense,
            "speed": char.speed,
        }

        user_card = db.query(UserCard).filter(
            UserCard.user_id == callback.from_user.id,
            UserCard.character_id == card_id,
        ).first()

        user_card_data = None
        if user_card:
            user_card_data = {
                "count": user_card.count,
                "is_favorite": user_card.is_favorite,
                "level": user_card.level,
            }

        total_users = db.query(User).count()
        owners_count = db.query(UserCard).filter(
            UserCard.character_id == card_id,
        ).distinct(UserCard.user_id).count()
        percentage = round((owners_count / total_users * 100), 2) if total_users > 0 else 0

    finally:
        db.close()

    # Формируем текст
    info = char_data["rarity_info"]
    stars = "⭐" * info["stars"]

    text = (
        f"🎴 <b>Информация о персонаже</b>\n\n"
        f"🆔 <b>ID:</b> <code>{char_data['id']}</code>\n"
        f"👤 <b>Имя:</b> {char_data['name']}"
    )

    if char_data['name_en'] and char_data['name_en'] != char_data['name']:
        text += f" (<i>{char_data['name_en']}</i>)"

    if char_data['name_jp']:
        text += f"\n🇯🇵 <i>{char_data['name_jp']}</i>"

    text += f"\n📺 <b>Тайтл:</b> {char_data['anime_title']}\n"
    text += f"💎 <b>Редкость:</b> {info['emoji']} {info['name']} {stars}\n"
    text += f"⚔️ <b>Статы:</b> ATK {char_data['power']} | DEF {char_data['defense']} | SPD {char_data['speed']}\n"

    if char_data['description']:
        text += f"\n📖 <i>{char_data['description']}</i>\n"

    text += "\n━━━━━━━━━━━━━━━━━━\n"

    if user_card_data:
        fav = " ⭐" if user_card_data["is_favorite"] else ""
        text += f"\n✅ <b>Есть у вас:</b> {user_card_data['count']} шт.{fav}"
    else:
        text += f"\n❌ <b>У вас нет этой карточки</b>"

    text += f"\n🌍 <b>Владельцев:</b> {owners_count} ({percentage}% игроков)"

    # Кнопки
    kb = InlineKeyboardBuilder()

    # Навигация по картинкам (если их несколько)
    nav_row = build_image_nav_row(char_data['id'], char_data['images'])
    if nav_row:
        kb.row(*nav_row)

    # Действия (только если есть карта)
    if user_card_data:
        action_row = []
        if user_card_data["is_favorite"]:
            action_row.append(InlineKeyboardButton(
                text="⭐ Убрать из избранного",
                callback_data=f"card_fav_{card_id}",
            ))
        else:
            action_row.append(InlineKeyboardButton(
                text="⭐ В избранное",
                callback_data=f"card_fav_{card_id}",
            ))
        kb.row(*action_row)

    kb.row(InlineKeyboardButton(
        text="⬅️ К коллекции",
        callback_data="coll_filter_all_1",
    ))

    if callback.message.chat.type == "private":
        add_game_button(kb, True, text="🎴 Открыть в приложении")

    # Отправка через хелпер
    await send_card_message(
        target=callback.message,
        text=text,
        image_url=char_data['image_url'],
        reply_markup=kb.as_markup(),
        edit=True,  # попробуем отредактировать/заменить
    )

    await callback.answer()


# Обработчик для избранного
@dp.callback_query(F.data.startswith("card_fav_"))
async def card_favorite_callback(callback: types.CallbackQuery):
    """Переключить избранное"""
    try:
        card_id = int(callback.data.split("_")[-1])
    except:
        await callback.answer("❌ Ошибка ID")
        return

    db = get_session()
    try:
        from database import UserCard

        # Убираем предыдущее избранное
        db.query(UserCard).filter(
            UserCard.user_id == callback.from_user.id,
            UserCard.is_favorite == True,
        ).update({"is_favorite": False})

        # Ставим текущее
        card = db.query(UserCard).filter(
            UserCard.user_id == callback.from_user.id,
            UserCard.character_id == card_id,
        ).first()

        if not card:
            await callback.answer("❌ Карточки нет в коллекции", show_alert=True)
            return

        card.is_favorite = True
        db.commit()

        await callback.answer("⭐ Карточка в избранном!", show_alert=False)
    finally:
        db.close()

    # Перезагружаем детали карточки
    await view_card_callback(callback)


@dp.callback_query(F.data == "noop")
async def noop_callback(callback: types.CallbackQuery):
    """Заглушка для нективных кнопок"""
    await callback.answer()


@dp.callback_query(F.data.startswith("coll_filter_"))
async def coll_filter_callback(callback: types.CallbackQuery):
    """Фильтр + пагинация: coll_filter_{rarity}_{page}"""
    parts = callback.data.split("_")

    if len(parts) >= 4:
        rarity = parts[2]
        try:
            page = int(parts[3])
        except:
            page = 1
    else:
        rarity = "all"
        page = 1

    # Если сообщение было с фото — удаляем и отправляем новое
    if callback.message.photo:
        try:
            await callback.message.delete()
        except:
            pass

        # Отправляем новое как ответ
        await show_collection_page(
            callback,
            page=page,
            edit=False,  # ← новое сообщение
            rarity_filter=rarity if rarity != "all" else None,
            sort_by="rarity_desc",
        )
    else:
        # Обычное текстовое — редактируем
        await show_collection_page(
            callback,
            page=page,
            edit=True,
            rarity_filter=rarity if rarity != "all" else None,
            sort_by="rarity_desc",
        )

    await callback.answer()


@dp.callback_query(F.data.startswith("coll_sort_"))
async def coll_sort_callback(callback: types.CallbackQuery):
    """Смена сортировки: coll_sort_{sort_key}_{rarity}_{page}"""
    parts = callback.data.split("_")

    if len(parts) < 5:
        await callback.answer("❌ Ошибка")
        return

    try:
        page = int(parts[-1])
        rarity = parts[-2]
        sort_key = "_".join(parts[2:-2])
    except:
        await callback.answer("❌ Ошибка параметров")
        return

    # Если сообщение с фото — удаляем и отправляем новое
    if callback.message.photo:
        try:
            await callback.message.delete()
        except:
            pass
        edit = False
    else:
        edit = True

    await show_collection_page(
        callback,
        page=page,
        edit=edit,
        rarity_filter=rarity if rarity != "all" else None,
        sort_by=sort_key,
    )
    await callback.answer("Сортировка обновлена")


def is_private_chat(message: types.Message) -> bool:
    """Проверка что чат приватный (не группа)"""
    return message.chat.type == "private"



def add_game_button(kb, is_private: bool, text: str = "🎴 Открыть игру"):
    """
    Универсальная кнопка открытия игры.
    В ЛС — WebApp внутри Telegram
    В группе — ссылка в ЛС бота
    """
    if not WEBAPP_URL or not WEBAPP_URL.startswith("https"):
        return

    if is_private:
        kb.row(InlineKeyboardButton(
            text=text,
            web_app=WebAppInfo(url=WEBAPP_URL),
        ))
    else:
        if BOT_USERNAME:
            kb.row(InlineKeyboardButton(
                text=f"{text} (в ЛС)",
                url=f"https://t.me/{BOT_USERNAME}",
            ))
        
BOT_USERNAME = None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db = get_session()
    try:
        gacha = GachaService(db)
        gacha.get_or_create_user(
            message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
    finally:
        db.close()

    is_private = is_private_chat(message)
    kb = InlineKeyboardBuilder()

    # Универсальная кнопка игры (сама разберётся ЛС/группа)
    add_game_button(kb, is_private)

    if is_private:
        # Callback-кнопки работают только в ЛС нормально
        kb.row(
            InlineKeyboardButton(text="💰 Забрать (2ч)", callback_data="claim"),
        )
        kb.row(
            InlineKeyboardButton(text="🎰 x1 (300💰)", callback_data="pull1"),
            InlineKeyboardButton(text="🎰 x3 (810💰)", callback_data="pull10"),
        )
        kb.row(InlineKeyboardButton(text="🎴 Коллекция", callback_data="my_collection"))
        kb.row(InlineKeyboardButton(text="🔍 Поиск", callback_data="search_start"))
        kb.row(InlineKeyboardButton(text="💼 Баланс", callback_data="balance"))

        if message.from_user.id == ADMIN_ID:
            kb.row(InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_menu"))

    await message.answer(
        "🎴 <b>Аниме Карточки</b>\n\n"
        "Собирай карточки любимых персонажей!\n\n"
        "💰 Обычный сбор — каждые 2 часа\n"
        "🎰 Крути гачу и собирай!\n\n"
        + ("Выбери действие 👇" if is_private else "Нажми чтобы играть 👇"),
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


def resolve_image_url(image_url: str):
    """Приводит относительный путь картинки к абсолютному URL (или None)."""
    if image_url and image_url.startswith("/"):
        if WEBAPP_URL and WEBAPP_URL.startswith("https"):
            image_url = WEBAPP_URL.rstrip("/") + image_url
        else:
            image_url = None
    return image_url


def build_image_nav_row(char_id: int, images: list, index: int = 0):
    """Строка навигации ◀ i/N ▶ для перелистывания картинок карточки. None если картинка одна."""
    if len(images) <= 1:
        return None
    total = len(images)
    prev_i = (index - 1) % total
    next_i = (index + 1) % total
    return [
        InlineKeyboardButton(text="◀", callback_data=f"imgnav_{char_id}_{prev_i}"),
        InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="noop"),
        InlineKeyboardButton(text="▶", callback_data=f"imgnav_{char_id}_{next_i}"),
    ]


async def send_card_message(
    target,
    text: str,
    image_url: str = None,
    reply_markup=None,
    edit: bool = False,
):
    """Универсальная отправка сообщения с карточкой."""

    image_url = resolve_image_url(image_url)
    has_image = image_url and image_url.startswith(("http://", "https://"))

    # Если нужно редактировать — сначала удаляем старое
    if edit:
        try:
            await target.delete()
        except Exception as e:
            print(f"⚠️ Delete failed: {e}")

    # С картинкой
    if has_image:
        try:
            await target.answer_photo(
                photo=image_url,
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            return
        except Exception as e:
            print(f"⚠️ Photo send error: {e}")

    # Без картинки
    await target.answer(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("imgnav_"))
async def image_nav_callback(callback: types.CallbackQuery):
    """Перелистывание картинок карточки кнопками ◀ ▶."""
    try:
        _, char_id_s, idx_s = callback.data.split("_")
        char_id, idx = int(char_id_s), int(idx_s)
    except Exception:
        await callback.answer()
        return

    db = get_session()
    try:
        from database import Character
        char = db.query(Character).get(char_id)
        images = [img.url for img in char.images] if char else []
        if not images and char and char.image_url:
            images = [char.image_url]
    finally:
        db.close()

    if not images or idx >= len(images):
        await callback.answer()
        return

    url = resolve_image_url(images[idx])
    if not url:
        await callback.answer("❌ Картинка недоступна", show_alert=True)
        return

    nav_row = build_image_nav_row(char_id, images, idx)
    old_rows = callback.message.reply_markup.inline_keyboard if callback.message.reply_markup else []
    new_markup = InlineKeyboardMarkup(inline_keyboard=[nav_row] + list(old_rows[1:]))

    try:
        await callback.message.edit_media(
            media=InputMediaPhoto(media=url, caption=callback.message.caption, parse_mode="HTML"),
            reply_markup=new_markup,
        )
    except Exception as e:
        print(f"⚠️ edit_media failed: {e}")

    await callback.answer()


# ============================================
# ДРОПЫ В ГРУППАХ (раз в DROP_INTERVAL_HOURS)
# ============================================
DROP_CHECK_SECONDS = 300     # как часто шедулер проверяет группы
DROP_CLAIM_TIMEOUT_SECONDS = 300  # сколько есть времени забрать дроп (5 мин)
DROP_EXPIRED_MARKER = -1     # claimed_by при истечении срока — отличаем от реального user_id


async def send_drop_to_chat(chat_id: int):
    """Кидает случайного персонажа в группу с кнопкой «Забрать»."""
    db = get_session()
    try:
        gacha = GachaService(db)
        character = gacha.roll_random_character()
        if not character:
            return

        info = character.rarity_info
        stars = "⭐" * info["stars"]
        caption = (
            f"🎁 <b>Дроп!</b>\n\n"
            f"{info['emoji']} <b>{character.display_name}</b>\n"
            f"{stars} {info['name']}\n"
            f"📺 {character.anime_title}\n\n"
            f"Кто успеет — тот и заберёт 👇\n"
            f"⏳ Забрать можно в течение 5 минут"
        )

        drop = Drop(chat_id=chat_id, character_id=character.id, message_id=0)
        db.add(drop)
        db.flush()

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🎁 Забрать", callback_data=f"claim_drop_{drop.id}"))

        image_url = resolve_image_url(character.image_url)
        message = None
        if image_url:
            try:
                message = await bot.send_photo(
                    chat_id=chat_id, photo=image_url, caption=caption,
                    reply_markup=kb.as_markup(), parse_mode="HTML",
                )
            except Exception as e:
                print(f"⚠️ Drop photo send error: {e}")

        if not message:
            message = await bot.send_message(
                chat_id=chat_id, text=caption,
                reply_markup=kb.as_markup(), parse_mode="HTML",
            )

        drop.message_id = message.message_id
        db.commit()

        asyncio.create_task(expire_drop(drop.id, chat_id, message.message_id))
    except Exception as e:
        print(f"⚠️ send_drop_to_chat({chat_id}) failed: {e}")
        db.rollback()
    finally:
        db.close()


async def expire_drop(drop_id: int, chat_id: int, message_id: int):
    """Если за DROP_CLAIM_TIMEOUT_SECONDS дроп не забрали — сообщение само пропадает."""
    await asyncio.sleep(DROP_CLAIM_TIMEOUT_SECONDS)

    db = get_session()
    try:
        # Атомарно: помечаем "истёк", только если ещё никто не забрал
        rows = db.query(Drop).filter(
            Drop.id == drop_id, Drop.claimed_by.is_(None)
        ).update(
            {"claimed_by": DROP_EXPIRED_MARKER, "claimed_at": datetime.utcnow()},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()

    if rows:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            print(f"⚠️ expire_drop delete failed: {e}")


async def drop_scheduler_loop():
    """Раз в DROP_CHECK_SECONDS проверяет группы и кидает дроп там, где прошло DROP_INTERVAL_HOURS."""
    interval = timedelta(hours=DROP_INTERVAL_HOURS)
    while True:
        try:
            db = get_session()
            try:
                now = datetime.utcnow()
                due = db.query(GroupChat).filter(
                    (GroupChat.last_drop_at.is_(None)) |
                    (GroupChat.last_drop_at <= now - interval)
                ).all()
                due_ids = [g.chat_id for g in due]
                for g in due:
                    g.last_drop_at = now
                db.commit()
            finally:
                db.close()

            for chat_id in due_ids:
                await send_drop_to_chat(chat_id)
        except Exception as e:
            print(f"⚠️ drop_scheduler_loop error: {e}")

        await asyncio.sleep(DROP_CHECK_SECONDS)


@dp.callback_query(F.data.startswith("claim_drop_"))
async def claim_drop_callback(callback: types.CallbackQuery):
    """Забрать выпавшего персонажа — первому нажавшему."""
    try:
        drop_id = int(callback.data.split("_")[-1])
    except Exception:
        await callback.answer()
        return

    db = get_session()
    try:
        from database import Character
        from sqlalchemy.orm import joinedload

        # Атомарный захват: обновляем, только если ещё никто не забрал
        claimed_rows = db.query(Drop).filter(
            Drop.id == drop_id, Drop.claimed_by.is_(None)
        ).update(
            {"claimed_by": callback.from_user.id, "claimed_at": datetime.utcnow()},
            synchronize_session=False,
        )
        db.commit()

        if claimed_rows == 0:
            await callback.answer("❌ Уже забрали", show_alert=True)
            return

        drop = db.query(Drop).options(
            joinedload(Drop.character).joinedload(Character.anime)
        ).get(drop_id)
        character = drop.character

        gacha = GachaService(db)
        result = gacha.grant_character_to_user(
            callback.from_user.id, character,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )

        claimer_name = callback.from_user.full_name or callback.from_user.username or "???"
        dupe_note = "" if result["is_new"] else f" (дубликат, +{result['duplicate_coins']}💰)"
        claim_text = f"\n\n✅ <b>Забрал(а):</b> {claimer_name}{dupe_note}"
        display_name = character.display_name
    finally:
        db.close()

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=(callback.message.caption or "") + claim_text,
                reply_markup=None,
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                text=(callback.message.text or "") + claim_text,
                reply_markup=None,
                parse_mode="HTML",
            )
    except Exception as e:
        print(f"⚠️ claim_drop edit failed: {e}")

    await callback.answer(f"🎁 Забрал(а): {display_name}!")


@dp.message(Command("dropnow"))
async def cmd_dropnow(message: types.Message):
    """Админ-команда для теста — кидает дроп в текущей группе прямо сейчас."""
    if message.from_user.id != ADMIN_ID:
        return
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группе.")
        return

    db = get_session()
    try:
        group = db.query(GroupChat).filter(GroupChat.chat_id == message.chat.id).first()
        if not group:
            group = GroupChat(chat_id=message.chat.id, title=message.chat.title)
            db.add(group)
        group.last_drop_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    await send_drop_to_chat(message.chat.id)


@dp.message(Command("myid"))
async def cmd_myid(message: types.Message):
    await message.answer(f"Твой Telegram ID: <code>{message.from_user.id}</code>", parse_mode="HTML")


@dp.message(Command("бонус", "bonus", "claim"))
async def cmd_claim(message: types.Message):
    """Быстрый сбор монет (каждые 2 часа)"""
    db = get_session()
    try:
        gacha = GachaService(db)
        result = gacha.claim_coins(message.from_user.id)
    finally:
        db.close()

    if result["success"]:
        await message.answer(
            f"💰 <b>+{result['claimed']} монет!</b>\n\n"
            f"💼 Баланс: <b>{result['coins']}</b>\n"
            f"⏰ Следующий сбор через 2 часа",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"⏰ <b>Рано!</b>\n\n"
            f"{result['message']}\n\n"
            f"💰 Баланс: <b>{result['coins']}</b>",
            parse_mode="HTML",
        )


@dp.callback_query(F.data == "claim")
async def claim_callback(callback: types.CallbackQuery):
    db = get_session()
    try:
        gacha = GachaService(db)
        result = gacha.claim_coins(callback.from_user.id)
    finally:
        db.close()
    await callback.answer(result["message"], show_alert=True)


@dp.callback_query(F.data == "pull1")
async def pull1_callback(callback: types.CallbackQuery):
    db = get_session()
    try:
        gacha = GachaService(db)
        result = gacha.single_pull(callback.from_user.id)
    finally:
        db.close()

    if not result["success"]:
        await callback.answer(result["message"], show_alert=True)
        return

    card = result["card"]
    if "error" in card:
        await callback.answer(card["error"], show_alert=True)
        return

    stars = "⭐" * card["stars"]
    new_mark = "🆕 НОВАЯ!" if card["is_new"] else "🔄 Дубликат"

    text = (
        f"🎰 <b>Результат:</b>\n\n"
        f"{card['emoji']} <b>{card['name']}</b>\n"
        f"{stars} {card['rarity_name']}\n"
        f"📺 {card['anime']}\n"
        f"⚔️{card['power']} 🛡{card['defense']} 💨{card['speed']}\n\n"
        f"{new_mark}\n"
        f"💰 Баланс: {result['coins']}"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🎰 Ещё x1", callback_data="pull1"),
        InlineKeyboardButton(text="🎰 x3", callback_data="pull10"),
    )

    await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "pull10")
async def pull10_callback(callback: types.CallbackQuery):
    db = get_session()
    try:
        gacha = GachaService(db)
        result = gacha.multi_pull(callback.from_user.id)
    finally:
        db.close()

    if not result["success"]:
        await callback.answer(result["message"], show_alert=True)
        return

    text = "🎰 <b>Результат x3:</b>\n\n"
    for card in result["cards"]:
        if "error" in card:
            continue
        new_mark = "🆕" if card["is_new"] else "🔄"
        text += f"{new_mark} {card['emoji']} <b>{card['name']}</b> — {card['rarity_name']}\n"

    text += f"\n✨ Новых: {result['new_count']}/3"
    text += f"\n💰 Баланс: {result['coins']}"

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🎰 Ещё x1", callback_data="pull1"),
        InlineKeyboardButton(text="🎰 Ещё x3", callback_data="pull10"),
    )

    await callback.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "balance")
async def balance_callback(callback: types.CallbackQuery):
    db = get_session()
    try:
        gacha = GachaService(db)
        info = gacha.get_user_info(callback.from_user.id)
    finally:
        db.close()

    await callback.message.answer(
        f"💼 <b>Профиль</b>\n\n"
        f"💰 Монеты: <b>{info['coins']}</b>\n"
        f"🎴 Карточек: <b>{info['total_cards']}</b>\n"
        f"🎰 Круток: <b>{info['total_pulls']}</b>\n"
        f"🎯 Pity: <b>{info['pulls_since_pity']}/90</b>",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "my_collection")
async def collection_callback(callback: types.CallbackQuery):
    db = get_session()
    try:
        gacha = GachaService(db)
        result = gacha.get_collection(callback.from_user.id, page=1, per_page=10)
    finally:
        db.close()

    if not result["cards"]:
        await callback.message.answer("🎴 Коллекция пуста! Начни крутить 🎰")
        await callback.answer()
        return

    text = f"🎴 <b>Коллекция</b> — {result['completion']}%\n\n"
    for card in result["cards"]:
        info = card["rarity_info"]
        stars = "⭐" * info["stars"]
        text += f"{info['emoji']} <b>{card['name']}</b> x{card['count']} {stars}\n"

    text += f"\n📊 {result['total_collected']}/{result['total_characters']}"

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ============================================
# КОМАНДЫ ДЛЯ /
# ============================================

@dp.message(Command("помощь", "help"))
async def cmd_help(message: types.Message):
    text = (
        "ℹ️ <b>Команды бота</b>\n\n"

        "🎴 <b>Основные:</b>\n"
        "/start — главное меню\n"
        "/bonus или /бонус — забрать монеты (2ч)\n"
        "/pull или /крутить — крутка x1 (300💰)\n"
        "/pull3 или /крутить3 — крутка x3 (810💰)\n\n"

        "🎴 <b>Коллекция:</b>\n"
        "/collection или /коллекция — мои карточки\n"
        "/card ID или /карта ID — <b>показать карточку</b>\n"
        "/search имя или /поиск имя — <b>найти персонажа по имени</b>\n"
        "/profile или /профиль — статистика\n\n"

        "💡 <b>Другое:</b>\n"
        "/suggest или /предложка — предложить карточку\n"
        "/help или /помощь — этот список\n"
    )

    if message.from_user.id == ADMIN_ID:
        text += "\n👑 <b>Админ:</b>\n/admin — админ-панель\n"

    await message.answer(text, parse_mode="HTML")


# ============================================
# ПОИСК ПЕРСОНАЖЕЙ
# ============================================
class SearchStates(StatesGroup):
    waiting_query = State()


def search_characters(db, query: str, limit: int = 10):
    """Ищет по имени, регистронезависимо. Фильтрация в Python, а не через SQL ILIKE —
    в SQLite lower()/ILIKE не умеет в юникод-регистр (кириллица, японский)."""
    from database import Character
    from sqlalchemy.orm import joinedload

    q = query.strip().lower()
    if not q:
        return []

    chars = db.query(Character).options(joinedload(Character.anime)).filter(
        Character.is_active == True
    ).all()
    matches = [
        c for c in chars
        if any(name and q in name.lower() for name in (c.name_en, c.name_ru, c.name_jp))
    ]
    return matches[:limit]


async def send_search_results(target, query: str, results: list):
    if not results:
        await target.answer(
            f"❌ Никого не найдено по запросу «{query}»",
            parse_mode="HTML",
        )
        return

    kb = InlineKeyboardBuilder()
    for c in results:
        info = c.rarity_info
        label = f"{info['emoji']} {c.display_name} ({c.anime_title})"
        kb.row(InlineKeyboardButton(text=label, callback_data=f"view_card_{c.id}"))

    await target.answer(
        f"🔍 <b>Найдено:</b> {len(results)}",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@dp.message(Command("search", "поиск", "найти"))
async def cmd_search(message: types.Message, state: FSMContext, command: CommandObject = None):
    if not command or not command.args:
        await message.answer("🔍 Введи имя персонажа для поиска (на любом языке):")
        await state.set_state(SearchStates.waiting_query)
        return

    db = get_session()
    try:
        results = search_characters(db, command.args)
    finally:
        db.close()

    await send_search_results(message, command.args, results)


@dp.message(SearchStates.waiting_query)
async def search_query_input(message: types.Message, state: FSMContext):
    await state.clear()

    db = get_session()
    try:
        results = search_characters(db, message.text or "")
    finally:
        db.close()

    await send_search_results(message, message.text, results)


@dp.callback_query(F.data == "search_start")
async def search_start_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("🔍 Введи имя персонажа для поиска (на любом языке):")
    await state.set_state(SearchStates.waiting_query)
    await callback.answer()


@dp.message(Command("бонус", "bonus", "claim"))
async def cmd_claim(message: types.Message):
    """Быстрый сбор монет (каждые 2 часа)"""
    db = get_session()
    try:
        gacha = GachaService(db)
        result = gacha.claim_coins(message.from_user.id)
    finally:
        db.close()

    if result["success"]:
        await message.answer(
            f"💰 <b>+{result['claimed']} монет!</b>\n\n"
            f"💼 Баланс: <b>{result['coins']}</b>\n"
            f"⏰ Следующий сбор через 2 часа",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"⏰ <b>Рано!</b>\n\n"
            f"{result['message']}\n\n"
            f"💰 Баланс: <b>{result['coins']}</b>",
            parse_mode="HTML",
        )


@dp.message(Command("крутить", "pull", "roll"))
async def cmd_pull(message: types.Message):
    db = get_session()
    try:
        gacha = GachaService(db)
        result = gacha.single_pull(message.from_user.id)
    finally:
        db.close()

    if not result["success"]:
        await message.answer(f"❌ {result['message']}", parse_mode="HTML")
        return

    card = result["card"]
    stars = "⭐" * card["stars"]
    new_mark = "🆕 <b>НОВАЯ!</b>" if card["is_new"] else "🔄 Дубликат"

    text = (
        f"🎰 <b>Крутка:</b>\n\n"
        f"{card['emoji']} <b>{card['name']}</b>\n"
        f"{stars} {card['rarity_name']}\n"
        f"📺 {card['anime']}\n"
        f"⚔️{card['power']} 🛡{card['defense']} 💨{card['speed']}\n\n"
        f"{new_mark}\n"
    )

    if not card["is_new"]:
        text += f"💰 Компенсация: +{card['duplicate_coins']}💰\n"

    text += f"\n💰 Баланс: {result['coins']}"

    kb = InlineKeyboardBuilder()
    if is_private_chat(message):
        kb.row(
            InlineKeyboardButton(text="🎰 Ещё x1", callback_data="pull1"),
            InlineKeyboardButton(text="🎰 x3", callback_data="pull10"),
        )
    kb.row(InlineKeyboardButton(
        text="🔍 Подробнее",
        callback_data=f"view_card_{card['id']}",
    ))

    # С картинкой если есть
    await send_card_message(
        target=message,
        text=text,
        image_url=card.get('image_url'),
        reply_markup=kb.as_markup() if kb.buttons else None,
        edit=False,
    )


@dp.message(Command("крутить3", "pull3", "roll3", "multi"))
async def cmd_pull3(message: types.Message):
    """Крутка x3"""
    db = get_session()
    try:
        gacha = GachaService(db)
        result = gacha.multi_pull(message.from_user.id)
    finally:
        db.close()

    if not result["success"]:
        await message.answer(f"❌ {result['message']}", parse_mode="HTML")
        return

    text = "🎰 <b>Результат x3:</b>\n\n"
    for card in result["cards"]:
        if "error" in card:
            continue
        new_mark = "🆕" if card["is_new"] else "🔄"
        text += f"{new_mark} {card['emoji']} <b>{card['name']}</b> — {card['rarity_name']}\n"

    text += f"\n✨ Новых: {result['new_count']}/3"
    text += f"\n💰 Баланс: {result['coins']}"

    await message.answer(text, parse_mode="HTML")


@dp.message(Command("card", "карта", "карточка"))
async def cmd_card(message: types.Message, command: CommandObject = None):
    """Показать подробную информацию о карточке по ID"""

    if not command or not command.args:
        await message.answer(
            "🎴 <b>Просмотр карточки</b>\n\n"
            "Использование: <code>/card ID</code>\n"
            "Пример: <code>/card 5</code>\n\n"
            "ID можно узнать в /collection",
            parse_mode="HTML",
        )
        return

    try:
        card_id = int(command.args.strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом.", parse_mode="HTML")
        return

    db = get_session()
    try:
        from database import Character, User, UserCard
        from sqlalchemy.orm import joinedload

        char = db.query(Character).options(
            joinedload(Character.anime)
        ).filter(Character.id == card_id).first()

        if not char:
            await message.answer(f"❌ Карточка #{card_id} не найдена")
            return

        char_data = {
            "id": char.id,
            "name": char.display_name,
            "name_en": char.name_en,
            "name_jp": char.name_jp,
            "anime_title": char.anime_title,
            "rarity": char.rarity,
            "rarity_info": char.rarity_info,
            "image_url": char.image_url,
            "images": [i.url for i in char.images] or ([char.image_url] if char.image_url else []),
            "description": char.description,
            "power": char.power,
            "defense": char.defense,
            "speed": char.speed,
        }

        user_card = db.query(UserCard).filter(
            UserCard.user_id == message.from_user.id,
            UserCard.character_id == card_id,
        ).first()

        user_card_data = {
            "count": user_card.count,
            "is_favorite": user_card.is_favorite,
        } if user_card else None

        total_users = db.query(User).count()
        owners_count = db.query(UserCard).filter(
            UserCard.character_id == card_id,
        ).distinct(UserCard.user_id).count()
        percentage = round((owners_count / total_users * 100), 2) if total_users > 0 else 0

    finally:
        db.close()

    info = char_data['rarity_info']
    stars = "⭐" * info['stars']

    text = (
        f"🎴 <b>Информация о персонаже</b>\n\n"
        f"🆔 <b>ID:</b> <code>{char_data['id']}</code>\n"
        f"👤 <b>Имя:</b> {char_data['name']}"
    )

    if char_data['name_en'] and char_data['name_en'] != char_data['name']:
        text += f" (<i>{char_data['name_en']}</i>)"

    if char_data['name_jp']:
        text += f"\n🇯🇵 <i>{char_data['name_jp']}</i>"

    text += f"\n📺 <b>Тайтл:</b> {char_data['anime_title']}\n"
    text += f"💎 <b>Редкость:</b> {info['emoji']} {info['name']} {stars}\n"
    text += f"⚔️ <b>Статы:</b> ATK {char_data['power']} | DEF {char_data['defense']} | SPD {char_data['speed']}\n"

    if char_data['description']:
        text += f"\n📖 <i>{char_data['description']}</i>\n"

    text += "\n━━━━━━━━━━━━━━━━━━\n\n"

    if user_card_data:
        fav = " ⭐" if user_card_data['is_favorite'] else ""
        text += f"✅ <b>Есть у вас:</b> {user_card_data['count']} шт.{fav}\n"
    else:
        text += f"❌ <b>У вас нет этой карточки</b>\n"

    text += f"🌍 <b>Владельцев:</b> {owners_count} ({percentage}% игроков)\n"

    kb = InlineKeyboardBuilder()

    nav_row = build_image_nav_row(char_data['id'], char_data['images'])
    if nav_row:
        kb.row(*nav_row)

    if user_card_data:
        fav_text = "⭐ Убрать" if user_card_data["is_favorite"] else "⭐ В избранное"
        kb.row(InlineKeyboardButton(
            text=fav_text,
            callback_data=f"card_fav_{card_id}",
        ))

    if is_private_chat(message):
        add_game_button(kb, True, text="🎴 Открыть в приложении")

    # Отправка через хелпер
    await send_card_message(
        target=message,
        text=text,
        image_url=char_data['image_url'],
        reply_markup=kb.as_markup() if kb.buttons else None,
        edit=False,  # новое сообщение
    )


@dp.message(Command("коллекция", "collection", "cards"))
async def cmd_collection(message: types.Message):
    """Показать коллекцию с группировкой"""
    await show_collection_page(message, page=1)


async def show_collection_page(
    message_or_callback,
    page: int = 1,
    edit: bool = False,
    rarity_filter: str = None,
    sort_by: str = "rarity_desc",
):
    """
    Универсальная функция показа страницы коллекции.
    """
    from sqlalchemy.orm import joinedload
    from sqlalchemy import case

    # Получаем user_id
    if isinstance(message_or_callback, types.CallbackQuery):
        user_id = message_or_callback.from_user.id
        user_name = message_or_callback.from_user.first_name or "Игрок"
        chat_type = message_or_callback.message.chat.type
    else:
        user_id = message_or_callback.from_user.id
        user_name = message_or_callback.from_user.first_name or "Игрок"
        chat_type = message_or_callback.chat.type

    is_pv = chat_type == "private"

    # Получаем данные и СРАЗУ конвертируем в dict внутри сессии
    db = get_session()
    try:
        from database import Character, UserCard, User, Anime, RARITY_INFO

        # joinedload — загружаем character сразу вместе с UserCard
        query = db.query(UserCard).join(Character).options(
            joinedload(UserCard.character).joinedload(Character.anime)
        ).filter(UserCard.user_id == user_id)

        # Фильтр по редкости
        if rarity_filter and rarity_filter != "all":
            query = query.filter(Character.rarity == rarity_filter)

        # Сортировка
        if sort_by == "rarity_desc":
            rarity_order = case(
                {r: info["order"] for r, info in RARITY_INFO.items()},
                value=Character.rarity,
                else_=0,
            )
            query = query.order_by(rarity_order.desc(), Character.anime_id, Character.name_en)
        elif sort_by == "rarity_asc":
            rarity_order = case(
                {r: info["order"] for r, info in RARITY_INFO.items()},
                value=Character.rarity,
                else_=0,
            )
            query = query.order_by(rarity_order.asc(), Character.anime_id, Character.name_en)
        elif sort_by == "name":
            query = query.order_by(Character.name_en)
        elif sort_by == "anime":
            query = query.order_by(Character.anime_id, Character.rarity.desc())
        elif sort_by == "count":
            query = query.order_by(UserCard.count.desc(), Character.rarity.desc())
        else:
            query = query.order_by(Character.name_en)

        # Счётчики
        total_filtered = query.count()
        per_page = 15
        total_pages = max(1, (total_filtered + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))

        # Получаем страницу
        cards_raw = query.offset((page - 1) * per_page).limit(per_page).all()

        # ============ КОНВЕРТИРУЕМ В DICT ВНУТРИ СЕССИИ ============
        cards = []
        for c in cards_raw:
            char = c.character
            cards.append({
                "id": char.id,
                "name": char.display_name,
                "anime": char.anime_title,
                "rarity": char.rarity,
                "rarity_info": char.rarity_info,
                "count": c.count,
                "is_favorite": c.is_favorite,
            })

        # Общая статистика
        total_chars = db.query(Character).filter(Character.is_active == True).count()
        all_user_cards = db.query(UserCard).filter(UserCard.user_id == user_id).count()
        total_animes = db.query(Anime).count()
        user_animes = db.query(Character.anime_id).join(UserCard).filter(
            UserCard.user_id == user_id,
        ).distinct().count()

    finally:
        db.close()

    # Дальше работаем ТОЛЬКО с dict — сессия уже не нужна

    # ============ ПРОВЕРКА ПУСТОЙ ============
    if not cards:
        if rarity_filter and rarity_filter != "all":
            filter_name = RARITY_INFO.get(rarity_filter, {}).get("name", rarity_filter)
            text = f"🎴 <b>Нет карточек редкости «{filter_name}»</b>\n\nПопробуй убрать фильтр."
        else:
            text = "🎴 <b>Коллекция пуста!</b>\n\nНачни крутить: /pull"

        kb = InlineKeyboardBuilder()
        if rarity_filter and rarity_filter != "all":
            kb.row(InlineKeyboardButton(
                text="🔄 Показать все",
                callback_data="coll_filter_all_1",
            ))

        reply_markup = kb.as_markup() if kb.buttons else None

        if edit and isinstance(message_or_callback, types.CallbackQuery):
            try:
                await message_or_callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
            except:
                pass
        else:
            answer_method = (
                message_or_callback.answer
                if hasattr(message_or_callback, 'answer') and not isinstance(message_or_callback, types.CallbackQuery)
                else message_or_callback.message.answer
            )
            await answer_method(text, reply_markup=reply_markup, parse_mode="HTML")
        return

    # ============ ФОРМИРУЕМ ТЕКСТ ============
    text = f"🎴 <b>{user_name}, ваша коллекция</b> "
    text += f"<i>(стр. {page}/{total_pages})</i>\n"

    # Инфа о фильтрах
    filter_info = []
    if rarity_filter and rarity_filter != "all":
        info = RARITY_INFO.get(rarity_filter, {})
        filter_info.append(f"{info.get('emoji', '')} {info.get('name', rarity_filter)}")

    sort_names = {
        "rarity_desc": "по редкости ↓",
        "rarity_asc": "по редкости ↑",
        "name": "по имени",
        "anime": "по аниме",
        "count": "по количеству",
    }
    filter_info.append(sort_names.get(sort_by, "по имени"))
    text += f"⚙️ <i>{' • '.join(filter_info)}</i>\n\n"

    # Отображение карточек
    if sort_by in ("rarity_desc", "rarity_asc"):
        # Простой список (для сортировки по редкости)
        for card in cards:
            info = card["rarity_info"]
            fav = "⭐ " if card["is_favorite"] else ""
            count_badge = f" ×{card['count']}" if card["count"] > 1 else ""

            text += (
                f"{info['emoji']} <b>{card['name']}</b>{count_badge} "
                f"{fav}| id: <code>{card['id']}</code>\n"
            )
    else:
        # Группировка по аниме
        grouped = {}
        for card in cards:
            anime = card["anime"]
            if anime not in grouped:
                grouped[anime] = []
            grouped[anime].append(card)

        for anime_name, anime_cards in grouped.items():
            text += f"🌸 <b>{anime_name}:</b>\n"
            for card in anime_cards:
                info = card["rarity_info"]
                fav = "⭐ " if card["is_favorite"] else ""
                count_badge = f" ×{card['count']}" if card["count"] > 1 else ""

                text += (
                    f"  {info['emoji']} <b>{card['name']}</b>{count_badge} "
                    f"{fav}| id: <code>{card['id']}</code>\n"
                )
            text += "\n"

    # Статистика
    percent = round(all_user_cards / max(total_chars, 1) * 100, 1)
    anime_percent = round(user_animes / max(total_animes, 1) * 100, 1)

    text += "━━━━━━━━━━━━━━━━━━\n"
    text += f"📊 Найдено <b>{all_user_cards}</b> из {total_chars} ({percent}%)\n"
    text += f"📺 Тайтлов: <b>{user_animes}</b> из {total_animes} ({anime_percent}%)"

    if rarity_filter and rarity_filter != "all":
        text += f"\n🔍 По фильтру: <b>{total_filtered}</b>"

    # ============ КНОПКИ ============
    kb = InlineKeyboardBuilder()

    # 1) Кнопки быстрого просмотра карточек
    card_buttons = []
    for card in cards:
        card_buttons.append(InlineKeyboardButton(
            text=f"🔍 {card['id']}",
            callback_data=f"view_card_{card['id']}",
        ))

    for i in range(0, len(card_buttons), 4):
        kb.row(*card_buttons[i:i+4])

    # 2) Пагинация
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(
            text="◀️",
            callback_data=f"coll_filter_{rarity_filter or 'all'}_{page-1}",
        ))
    nav_row.append(InlineKeyboardButton(
        text=f"{page}/{total_pages}",
        callback_data="noop",
    ))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(
            text="▶️",
            callback_data=f"coll_filter_{rarity_filter or 'all'}_{page+1}",
        ))
    kb.row(*nav_row)

    # 3) Фильтры по редкости
    current_filter = rarity_filter or "all"

    row1 = [
        InlineKeyboardButton(
            text="🔄" + (" ✓" if current_filter == "all" else ""),
            callback_data="coll_filter_all_1",
        ),
    ]

    rarity_order_list = ["secret", "mythical", "legendary", "epic", "rare", "uncommon", "common", "unique"]

    filter_buttons = []
    for rarity_key in rarity_order_list:
        if rarity_key not in RARITY_INFO:
            continue
        info = RARITY_INFO[rarity_key]
        active = "✓" if current_filter == rarity_key else ""
        filter_buttons.append(InlineKeyboardButton(
            text=f"{info['emoji']}{active}",
            callback_data=f"coll_filter_{rarity_key}_1",
        ))

    kb.row(*(row1 + filter_buttons[:4]))
    if len(filter_buttons) > 4:
        kb.row(*filter_buttons[4:8])

    # 4) Сортировка
    sort_options = [
        ("rarity_desc", "💎↓"),
        ("rarity_asc", "💎↑"),
        ("name", "🔤"),
        ("anime", "📺"),
        ("count", "🔢"),
    ]

    sort_buttons = []
    for sort_key, sort_emoji in sort_options:
        active = "✓" if sort_by == sort_key else ""
        sort_buttons.append(InlineKeyboardButton(
            text=f"{sort_emoji}{active}",
            callback_data=f"coll_sort_{sort_key}_{rarity_filter or 'all'}_{page}",
        ))
    kb.row(*sort_buttons)

    # 5) Открыть в приложении (ЛС)
    if is_pv:
        add_game_button(kb, True, text="🎴 Открыть в приложении")

    # ============ ОТПРАВКА ============
    reply_markup = kb.as_markup() if kb.buttons else None

    if edit and isinstance(message_or_callback, types.CallbackQuery):
        # Пытаемся отредактировать
        try:
            # Если сообщение было с фото — редактировать нельзя, отправляем новое
            if message_or_callback.message.photo:
                # Удаляем старое сообщение с фото
                try:
                    await message_or_callback.message.delete()
                except:
                    pass

                # Отправляем новое
                await message_or_callback.message.answer(
                    text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            else:
                # Обычное текстовое — редактируем
                await message_or_callback.message.edit_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
        except Exception as e:
            print(f"⚠️ Edit failed: {e}")
            # Fallback — отправить как новое
            try:
                await message_or_callback.message.answer(
                    text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            except Exception as e2:
                print(f"⚠️ Send failed too: {e2}")
    else:
        # Новое сообщение
        answer_method = (
            message_or_callback.answer
            if hasattr(message_or_callback, 'answer') and not isinstance(message_or_callback, types.CallbackQuery)
            else message_or_callback.message.answer
        )
        await answer_method(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )


@dp.message(Command("профиль", "profile", "balance", "me"))
async def cmd_profile(message: types.Message):
    """Профиль игрока с избранной карточкой"""

    db = get_session()
    try:
        gacha = GachaService(db)
        info = gacha.get_user_info(message.from_user.id)

        # Получаем избранную карточку
        from database import UserCard, Character
        from sqlalchemy.orm import joinedload

        fav = db.query(UserCard).options(
            joinedload(UserCard.character).joinedload(Character.anime)
        ).filter(
            UserCard.user_id == message.from_user.id,
            UserCard.is_favorite == True,
        ).first()

        fav_data = None
        if fav and fav.character:
            fav_data = {
                "id": fav.character.id,
                "name": fav.character.display_name,
                "anime": fav.character.anime_title,
                "rarity": fav.character.rarity,
                "rarity_info": fav.character.rarity_info,
                "image_url": fav.character.image_url,
                "count": fav.count,
            }
    finally:
        db.close()

    name = message.from_user.first_name or "Игрок"
    username = f"@{message.from_user.username}" if message.from_user.username else ""

    # Формируем текст
    text = f"💼 <b>Профиль</b>\n\n"
    text += f"👤 <b>{name}</b>"
    if username:
        text += f" {username}"
    text += f"\n🆔 <code>{message.from_user.id}</code>\n\n"

    text += f"💰 Монеты: <b>{info['coins']:,}</b>\n".replace(",", " ")
    text += f"🎴 Карточек: <b>{info['total_cards']}</b>\n"
    text += f"🎰 Круток: <b>{info['total_pulls']}</b>\n"
    text += f"🎯 Pity: <b>{info['pulls_since_pity']}/90</b>\n"

    # Если есть избранная
    if fav_data:
        info_r = fav_data["rarity_info"]
        stars = "⭐" * info_r["stars"]
        text += f"\n━━━━━━━━━━━━━━━━━━\n"
        text += f"⭐ <b>Избранная карточка:</b>\n"
        text += f"{info_r['emoji']} <b>{fav_data['name']}</b> {stars}\n"
        text += f"📺 {fav_data['anime']}"
        if fav_data['count'] > 1:
            text += f"\n📚 Копий: {fav_data['count']}"

    # Кнопки
    kb = InlineKeyboardBuilder()

    if fav_data:
        kb.row(InlineKeyboardButton(
            text=f"🔍 Открыть карточку #{fav_data['id']}",
            callback_data=f"view_card_{fav_data['id']}",
        ))

    if is_private_chat(message):
        add_game_button(kb, True, text="🎴 Открыть в приложении")

    # Отправка с картинкой избранной если есть
    if fav_data and fav_data.get('image_url'):
        await send_card_message(
            target=message,
            text=text,
            image_url=fav_data['image_url'],
            reply_markup=kb.as_markup() if kb.buttons else None,
            edit=False,
        )
    else:
        # Без картинки
        if not fav_data:
            text += "\n\n💡 Выбери избранную карточку в коллекции!\n"
            text += "<i>Нажми ⭐ на любой карточке из /collection</i>"

        await message.answer(
            text,
            reply_markup=kb.as_markup() if kb.buttons else None,
            parse_mode="HTML",
        )


@dp.message(Command("предложка", "suggest"))
async def cmd_suggest(message: types.Message):
    kb = InlineKeyboardBuilder()
    add_game_button(kb, is_private_chat(message), text="💡 Открыть форму")

    await message.answer(
        "💡 <b>Предложи персонажа!</b>\n\n"
        "Открой приложение → таб «💡 Предложка»\n"
        "Заполни форму → отправь\n"
        "За одобрение получишь <b>+500 💰</b>",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )


@dp.message(Command("помощь", "help"))
async def cmd_help(message: types.Message):
    """Список всех команд"""
    text = (
        "ℹ️ <b>Команды бота</b>\n\n"
        "🎴 <b>Основные:</b>\n"
        "/start — главное меню\n"
        "/бонус — забрать монеты (раз в 2ч)\n"
        "/крутить — крутка x1 (300💰)\n"
        "/крутить3 — крутка x3 (810💰)\n\n"
        "🎴 <b>Коллекция:</b>\n"
        "/коллекция — мои карточки\n"
        "/профиль — статистика\n\n"
        "💡 <b>Другое:</b>\n"
        "/предложка — предложить новую карточку\n"
        "/помощь — этот список\n"
    )

    if message.from_user.id == ADMIN_ID:
        text += (
            "\n👑 <b>Админ:</b>\n"
            "/admin или /admins — админ-панель\n"
        )

    await message.answer(text, parse_mode="HTML")

# ===========

@dp.callback_query(F.data == "admin_menu")
async def admin_btn(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    try:
        from admin import admin_menu
        await admin_menu(callback.message)
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка админки: {e}")

@dp.message(Command("admin"))
async def cmd_admin_link(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not WEBAPP_URL or not WEBAPP_URL.startswith("https://"):
        await message.answer("❌ Веб-админка временно недоступна.")
        return

    admin_url = f"{WEBAPP_URL.rstrip('/')}/admin"
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="📱 Открыть веб-админку",
        web_app=WebAppInfo(url=admin_url),
    ))

    await message.answer(
        "👑 <b>Админ-панель</b>\n\n"
        "Доступ подтверждается автоматически через Telegram.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
    )

async def notify_suggestion_result(user_id: int, status: str, comment: str = None,
                                    reward: int = 0, char_name: str = None):
    """Уведомление о результате рассмотрения"""
    try:
        if status == "approved":
            text = (
                f"✅ <b>Твоё предложение одобрено!</b>\n\n"
                f"🎴 Карточка <b>{char_name}</b> добавлена в игру!\n"
                f"💰 Награда: <b>+{reward} монет</b>\n"
            )
            if comment:
                text += f"\n💬 Комментарий админа:\n<i>{comment}</i>"
        else:
            text = (
                f"❌ <b>Твоё предложение отклонено</b>\n\n"
                f"💬 Причина:\n<i>{comment or 'Не указана'}</i>\n\n"
                f"Не расстраивайся, попробуй ещё! 💪"
            )

        await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception as e:
        print(f"⚠️ Не смог уведомить {user_id}: {e}")


async def notify_admin_new_suggestion(user_name: str, char_name: str, anime: str):
    """Уведомление админу о новом предложении"""
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📬 <b>Новое предложение карточки!</b>\n\n"
            f"👤 От: <b>{user_name}</b>\n"
            f"🎴 <b>{char_name}</b>\n"
            f"📺 {anime}\n\n"
            f"Открой /admin для рассмотрения",
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"⚠️ Не смог уведомить админа: {e}")

async def on_startup(bot: Bot):
    """Инициализация при запуске бота"""
    global BOT_USERNAME, BOT_LOOP
    BOT_LOOP = asyncio.get_running_loop()

    me = await bot.get_me()
    BOT_USERNAME = me.username
    print(f"✅ Bot username: @{BOT_USERNAME}")

    # ========== 1. Menu Button ==========
    try:
        if WEBAPP_URL and WEBAPP_URL.startswith("https"):
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="🎴 Играть",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                )
            )
            print(f"✅ Menu button установлена: {WEBAPP_URL}")
        else:
            print(f"⚠️ WEBAPP_URL некорректный: {WEBAPP_URL}")
    except Exception as e:
        print(f"❌ Menu button error: {e}")

    # ========== 2. Команды бота ==========
    from aiogram.types import (
        BotCommand,
        BotCommandScopeChat,
        BotCommandScopeAllPrivateChats,
        BotCommandScopeAllGroupChats,
    )

    # ⚠️ ВАЖНО: команды ТОЛЬКО на английском!
    # Русские алиасы (/бонус, /крутить) работают из кода,
    # но в меню Telegram их нельзя.
    commands = [
        BotCommand(command="start",      description="🎴 Главное меню"),
        BotCommand(command="bonus",      description="💰 Забрать монеты (2ч)"),
        BotCommand(command="pull",       description="🎰 Крутка x1 (300💰)"),
        BotCommand(command="pull3",      description="🎰 Крутка x3 (810💰)"),
        BotCommand(command="collection", description="🎴 Моя коллекция"),
        BotCommand(command="card",       description="🔍 Показать карточку по ID"),
        BotCommand(command="search",     description="🔎 Поиск персонажа по имени"),
        BotCommand(command="profile",    description="💼 Мой профиль"),
        BotCommand(command="suggest",    description="💡 Предложить карточку"),
        BotCommand(command="help",       description="ℹ️ Список команд"),
    ]

    try:
        # Сбрасываем старые команды
        await bot.delete_my_commands()

        # Ставим общие
        await bot.set_my_commands(commands)
        print(f"✅ Установлено команд: {len(commands)}")

        # Дополнительно для админа
        admin_commands = commands + [
            BotCommand(command="admin", description="👑 Админ-панель"),
            BotCommand(command="admins", description="👑 Админ-панель"),
        ]
        await bot.set_my_commands(
            admin_commands,
            scope=BotCommandScopeChat(chat_id=ADMIN_ID),
        )
        print(f"✅ У админа: {len(admin_commands)} команд")

    except Exception as e:
        print(f"❌ Commands error: {e}")

    # ========== 3. Шедулер дропов в группах ==========
    asyncio.create_task(drop_scheduler_loop())
    print(f"✅ Шедулер дропов запущен (раз в {DROP_INTERVAL_HOURS}ч, проверка каждые {DROP_CHECK_SECONDS}с)")


dp.startup.register(on_startup)

async def main():
    logging.info("🚀 Запуск Anicard...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
