# seed.py
from database import get_session, Character, Anime

def seed_if_empty():
    db = get_session()
    if db.query(Character).count() > 0:
        print("📦 БД уже заполнена")
        db.close()
        return

    print("🌱 Загружаем начальных персонажей...")

    DATA = [
        ("Naruto", "Наруто", [
            ("Naruto Uzumaki", "Наруто Узумаки", "legendary", 95, 70, 85),
            ("Sasuke Uchiha", "Саске Учиха", "legendary", 93, 75, 90),
            ("Sakura Haruno", "Сакура Харуно", "epic", 80, 65, 70),
            ("Kakashi Hatake", "Какаши Хатаке", "legendary", 90, 80, 88),
            ("Itachi Uchiha", "Итачи Учиха", "mythical", 97, 85, 92),
            ("Hinata Hyuga", "Хината Хьюга", "epic", 72, 68, 75),
            ("Rock Lee", "Рок Ли", "rare", 85, 60, 95),
            ("Gaara", "Гаара", "legendary", 88, 95, 65),
            ("Jiraiya", "Джирайя", "mythical", 92, 78, 80),
            ("Minato Namikaze", "Минато Намикадзе", "mythical", 95, 78, 100),
            ("Shikamaru Nara", "Шикамару Нара", "rare", 55, 50, 60),
            ("Neji Hyuga", "Нэдзи Хьюга", "rare", 82, 78, 85),
            ("Tenten", "Тентен", "uncommon", 65, 55, 70),
            ("Kiba Inuzuka", "Киба Инузука", "uncommon", 68, 52, 78),
            ("Konohamaru", "Конохамару", "common", 45, 40, 55),
            ("Iruka Umino", "Ирука Умино", "common", 40, 45, 50),
        ]),
        ("Attack on Titan", "Атака титанов", [
            ("Levi Ackerman", "Леви Аккерман", "mythical", 99, 85, 99),
            ("Eren Yeager", "Эрен Йегер", "legendary", 94, 80, 78),
            ("Mikasa Ackerman", "Микаса Аккерман", "legendary", 96, 82, 93),
            ("Erwin Smith", "Эрвин Смит", "legendary", 78, 70, 72),
            ("Armin Arlert", "Армин Арлерт", "epic", 60, 45, 55),
            ("Hange Zoe", "Ханджи Зоэ", "epic", 72, 65, 70),
            ("Annie Leonhart", "Энни Леонхарт", "legendary", 88, 90, 85),
            ("Jean Kirstein", "Жан Кирштайн", "rare", 70, 65, 72),
            ("Sasha Blouse", "Саша Браус", "rare", 68, 55, 80),
            ("Connie Springer", "Конни Спрингер", "uncommon", 60, 50, 75),
            ("Marco Bott", "Марко Ботт", "common", 50, 50, 55),
        ]),
        ("Jujutsu Kaisen", "Магическая битва", [
            ("Satoru Gojo", "Сатору Годжо", "secret", 100, 100, 95),
            ("Ryomen Sukuna", "Рёмен Сукуна", "secret", 100, 98, 97),
            ("Yuji Itadori", "Юдзи Итадори", "legendary", 90, 80, 88),
            ("Megumi Fushiguro", "Мегуми Фушигуро", "legendary", 85, 75, 82),
            ("Nobara Kugisaki", "Нобара Кугисаки", "epic", 78, 65, 75),
            ("Yuta Okkotsu", "Юта Оккоцу", "mythical", 95, 88, 85),
            ("Kento Nanami", "Кэнто Нанами", "legendary", 88, 82, 78),
            ("Toge Inumaki", "Тогэ Инумаки", "epic", 72, 55, 70),
            ("Maki Zenin", "Маки Дзэнин", "epic", 82, 78, 85),
            ("Panda", "Панда", "rare", 80, 85, 65),
            ("Aoi Todo", "Аой Тодо", "epic", 90, 78, 80),
        ]),
        ("Demon Slayer", "Истребитель демонов", [
            ("Muzan Kibutsuji", "Музан Кибуцуджи", "secret", 100, 95, 90),
            ("Tanjiro Kamado", "Танджиро Камадо", "legendary", 88, 75, 85),
            ("Nezuko Kamado", "Нэзуко Камадо", "legendary", 82, 90, 80),
            ("Rengoku Kyojuro", "Ренгоку Кёджуро", "mythical", 95, 80, 90),
            ("Zenitsu Agatsuma", "Зеницу Агацума", "epic", 75, 50, 98),
            ("Inosuke Hashibira", "Иноскэ Хашибира", "epic", 83, 72, 82),
            ("Giyu Tomioka", "Гию Томиока", "legendary", 90, 85, 88),
            ("Shinobu Kocho", "Шинобу Кочо", "legendary", 78, 60, 95),
            ("Kanao Tsuyuri", "Канао Цуюри", "epic", 80, 72, 88),
            ("Muichiro Tokito", "Муичиро Токито", "legendary", 85, 70, 92),
        ]),
        ("One Piece", "Ван Пис", [
            ("Monkey D. Luffy", "Монки Д. Луффи", "mythical", 97, 85, 90),
            ("Shanks", "Шанкс", "secret", 99, 92, 95),
            ("Kaido", "Кайдо", "secret", 100, 100, 75),
            ("Roronoa Zoro", "Ророноа Зоро", "legendary", 95, 88, 82),
            ("Sanji", "Санджи", "legendary", 90, 75, 92),
            ("Nami", "Нами", "epic", 55, 45, 70),
            ("Portgas D. Ace", "Портгас Д. Эйс", "mythical", 92, 75, 88),
            ("Boa Hancock", "Боа Хэнкок", "legendary", 88, 80, 85),
            ("Usopp", "Усопп", "rare", 50, 40, 65),
            ("Tony Tony Chopper", "Чоппер", "rare", 60, 55, 58),
            ("Nico Robin", "Нико Робин", "epic", 70, 60, 65),
            ("Franky", "Фрэнки", "rare", 75, 82, 55),
            ("Brook", "Брук", "rare", 65, 50, 78),
        ]),
    ]

    total = 0
    for title_en, title_ru, chars in DATA:
        anime = Anime(title_en=title_en, title_ru=title_ru)
        db.add(anime)
        db.flush()
        for name_en, name_ru, rarity, power, defense, speed in chars:
            db.add(Character(
                name_en=name_en, name_ru=name_ru, anime_id=anime.id,
                rarity=rarity, power=power, defense=defense, speed=speed,
            ))
            total += 1

    db.commit()
    db.close()
    print(f"✅ Загружено {total} персонажей!")

def enrich_missing_character_images():
    """Fill empty seed-card artwork using AniList's public character images."""
    import re
    from import_anilist import search_anime, get_anime_with_characters
    from database import CharacterImage

    def normalize(value):
        return re.sub(r"[^a-z0-9]+", "", (value or "").lower())

    db = get_session()
    try:
        anime_rows = db.query(Anime).all()
        missing = db.query(Character).filter(
            (Character.image_url.is_(None)) | (Character.image_url == "")
        ).count()
    finally:
        db.close()

    if not missing:
        print("🖼 Все карточки уже имеют изображения")
        return

    print(f"🖼 Ищем изображения для карточек без арта: {missing}")
    updated = 0

    for anime_row in anime_rows:
        try:
            candidates = search_anime(anime_row.title_en, limit=5)
            if not candidates:
                continue

            wanted = normalize(anime_row.title_en)
            exact = []
            for candidate in candidates:
                title = candidate.get("title") or {}
                names = [title.get("english"), title.get("romaji")]
                if any(wanted and (wanted in normalize(name) or normalize(name) in wanted) for name in names if name):
                    exact.append(candidate)
            if not exact:
                print(f"⚠️ AniList: точное совпадение для {anime_row.title_en} не найдено")
                continue
            media = exact[0]

            data = get_anime_with_characters(media["id"], chars_limit=50)
            if not data:
                continue

            by_name = {}
            for edge in (data.get("characters") or {}).get("edges") or []:
                node = edge.get("node") or {}
                names = node.get("name") or {}
                aliases = [names.get("full"), names.get("native")]
                alternative = names.get("alternative") or []
                aliases.extend(alternative if isinstance(alternative, list) else [alternative])
                image = (node.get("image") or {}).get("large")
                if not image or not image.startswith("https://"):
                    continue
                for alias in aliases:
                    key = normalize(alias)
                    if key:
                        by_name[key] = image

            db = get_session()
            try:
                chars = db.query(Character).filter(
                    Character.anime_id == anime_row.id,
                    (Character.image_url.is_(None)) | (Character.image_url == ""),
                ).all()
                for char in chars:
                    image = by_name.get(normalize(char.name_en)) or by_name.get(normalize(char.name_ru))
                    if not image:
                        continue
                    char.image_url = image
                    if not db.query(CharacterImage).filter(
                        CharacterImage.character_id == char.id
                    ).first():
                        db.add(CharacterImage(
                            character_id=char.id,
                            url=image,
                            position=0,
                        ))
                    updated += 1
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            print(f"⚠️ Не удалось получить арты для {anime_row.title_en}: {exc}")

    print(f"🖼 AniList: добавлено изображений для {updated} карточек")
