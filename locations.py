from typing import Any

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

OTHER_COUNTRY = "Інша країна"
OTHER_CITY = "Інше місто"

COUNTRIES = [
    "Україна",
    "Польща",
    "Німеччина",
    "Чехія",
    "Словаччина",
    "Угорщина",
    "Румунія",
    "Молдова",
    "Литва",
    "Латвія",
    "Італія",
    "Іспанія",
    "Франція",
    "Нідерланди",
    "Бельгія",
    "Австрія",
    "Греція",
    "Туреччина",
    "Болгарія",
    "Сербія",
]

CITIES = {
    "Україна": [
        "Київ",
        "Львів",
        "Одеса",
        "Харків",
        "Дніпро",
        "Запоріжжя",
        "Вінниця",
        "Чернівці",
        "Луцьк",
        "Рівне",
        "Тернопіль",
        "Івано-Франківськ",
        "Ужгород",
        "Хмельницький",
        "Полтава",
        "Миколаїв",
        "Черкаси",
        "Житомир",
    ],
    "Польща": [
        "Варшава",
        "Краків",
        "Вроцлав",
        "Гданськ",
        "Познань",
        "Лодзь",
        "Катовіце",
        "Люблін",
        "Щецин",
        "Перемишль",
        "Жешув",
        "Бяла-Подляска",
    ],
    "Німеччина": [
        "Берлін",
        "Мюнхен",
        "Гамбург",
        "Франкфурт",
        "Кельн",
        "Дюссельдорф",
        "Штутгарт",
        "Лейпциг",
        "Дрезден",
        "Ганновер",
    ],
    "Чехія": ["Прага", "Брно", "Острава", "Пльзень"],
    "Словаччина": ["Братислава", "Кошице", "Жиліна"],
    "Угорщина": ["Будапешт", "Дебрецен", "Сегед", "Дьєр"],
    "Румунія": ["Бухарест", "Клуж-Напока", "Тімішоара", "Констанца", "Ясси"],
    "Молдова": ["Кишинів", "Бельці"],
    "Литва": ["Вільнюс", "Каунас", "Клайпеда"],
    "Латвія": ["Рига", "Даугавпілс", "Лієпая"],
    "Італія": ["Мілан", "Рим", "Турин", "Верона", "Неаполь", "Болонья", "Венеція", "Генуя"],
    "Іспанія": ["Мадрид", "Барселона", "Валенсія", "Севілья", "Більбао"],
    "Франція": ["Париж", "Ліон", "Марсель", "Лілль", "Страсбург"],
    "Нідерланди": ["Роттердам", "Амстердам", "Ейндговен", "Утрехт"],
    "Бельгія": ["Антверпен", "Брюссель", "Льєж", "Гент"],
    "Австрія": ["Відень", "Зальцбург", "Лінц", "Грац"],
    "Греція": ["Афіни", "Салоніки", "Патри", "Пірей", "Іракліон"],
    "Туреччина": ["Стамбул", "Анкара", "Ізмір", "Бурса", "Мерсін", "Анталія"],
    "Болгарія": ["Софія", "Пловдив", "Варна", "Бургас"],
    "Сербія": ["Белград", "Нові-Сад", "Ніш"],
}


def _rows(items: list[str]) -> list[list[KeyboardButton]]:
    rows: list[list[KeyboardButton]] = []
    row: list[KeyboardButton] = []
    for item in items:
        row.append(KeyboardButton(text=item))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def country_keyboard() -> ReplyKeyboardMarkup:
    rows = _rows(COUNTRIES)
    rows.append([KeyboardButton(text=OTHER_COUNTRY)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def city_keyboard(country: str) -> ReplyKeyboardMarkup:
    cities = list(CITIES.get(country) or [])
    rows = _rows(cities)
    rows.append([KeyboardButton(text=OTHER_CITY)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def format_place(country: str, city: str) -> str:
    country = (country or "").strip()
    city = (city or "").strip()
    if country and city:
        return f"{country}, {city}"
    return country or city


def format_volume(volume: Any) -> str:
    value = str(volume or "").strip()
    if not value or value in {"-", "—", "–"}:
        return "—"
    if "м³" in value or "м3" in value:
        return value
    return f"{value} м³"


def skip_optional(text: str) -> bool:
    return text.strip() in {"-", "—", "–"}
