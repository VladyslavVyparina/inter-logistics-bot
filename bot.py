import asyncio
import html as html_lib
import logging
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

from config import (
    BOT_TOKEN,
    BOT_USERNAME,
    CHANNEL_ID,
    CHAT_ID,
    REPOST_GROUP_IDS,
    SOURCE_GROUP_IDS,
    TRANSPORT_CHANNEL_ID,
    TRANSPORT_CHAT_ID,
    TRANSPORT_PUSH_EXTRA_CHAT_ID,
)
from google_sheets import append_row
from listings import get_listing, save_listing
from locations import (
    format_place,
    format_volume,
    skip_optional,
)
from scheduler import channel_push_scheduler, send_channel_push
from text_utils import (
    extract_phones,
    is_free_transport,
    looks_like_our_repost,
    strip_contacts,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


class RetryingSession(AiohttpSession):
    async def make_request(self, bot, method, timeout=None):
        last_error = None
        for attempt in range(3):
            try:
                return await super().make_request(bot, method, timeout=timeout)
            except TelegramNetworkError as e:
                last_error = e
                log.warning("Telegram timeout, повтор %s/3", attempt + 1)
                await asyncio.sleep(1.5 * (attempt + 1))
        raise last_error

KYIV_TZ = ZoneInfo("Europe/Kyiv")

ADD_VEHICLE_BUTTON = "Додати авто"
ADD_CARGO_BUTTON = "Додати вантаж"
LOCATION_PROMPT = "🌍 Введіть країну та місто дислокації:"
DIRECTION_PROMPT = "🛣 Вкажіть країни або міста, куди готові їхати:"
CARGO_FROM_PROMPT = "🌍 Введіть країну та місто відправлення:"
CARGO_TO_PROMPT = "📍 Введіть країну та місто отримання:"

CARGO_VEHICLE_TYPES = [
    "Тент",
    "Рефрижератор",
    "Контейнер",
    "Відкритий",
    "Автовоз",
    "Цистерна",
    "Інше",
]
TRANSPORT_VEHICLE_TYPES = [
    "Тент",
    "Рефрижератор",
    "Контейнеровіз",
    "Відкритий",
    "Автовоз",
    "Цистерна",
    "Інше",
]

STATE: dict[int, dict[str, Any]] = {}
KNOWN_GROUPS: set[int] = set()
SEEN_GROUP_MESSAGES: set[tuple[int, int]] = set()
SEEN_LIMIT = 3000


def h(value: Any) -> str:
    return html_lib.escape(str(value or ""), quote=False)


def now_kyiv_str() -> str:
    return datetime.now(KYIV_TZ).strftime("%Y-%m-%d %H:%M:%S")


def transport_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ADD_VEHICLE_BUTTON, callback_data="add_vehicle")]
        ]
    )


def vehicle_keyboard(types: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    row: list[KeyboardButton] = []
    for item in types:
        row.append(KeyboardButton(text=item))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Надіслати номер телефону", request_contact=True)],
        ],
        resize_keyboard=True,
    )


def cargo_funnel_url(listing_id: str = "") -> str:
    start = f"t_{listing_id}" if listing_id else "logistics"
    return f"https://t.me/{BOT_USERNAME}?start={start}"


def transport_funnel_url() -> str:
    return f"https://t.me/{BOT_USERNAME}?start=transport"


def transport_url_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ADD_VEHICLE_BUTTON, url=transport_funnel_url())]
        ]
    )


def public_listing_keyboard(listing_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ADD_CARGO_BUTTON,
                    url=cargo_funnel_url(listing_id),
                )
            ]
        ]
    )


def clear_state(user_id: int) -> None:
    STATE.pop(user_id, None)


def parse_start_payload(text: str) -> str:
    parts = (text or "").split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def listing_id_from_payload(payload: str) -> str:
    if payload.startswith("t_"):
        return payload[2:]
    return ""


INTERNAL_CHAT_IDS = {
    CHAT_ID,
    TRANSPORT_CHAT_ID,
    CHANNEL_ID,
    TRANSPORT_CHANNEL_ID,
    TRANSPORT_PUSH_EXTRA_CHAT_ID,
    0,
    None,
}


def remember_group(chat_id: int) -> None:
    if chat_id not in INTERNAL_CHAT_IDS:
        KNOWN_GROUPS.add(chat_id)


def remember_message(chat_id: int, message_id: int) -> bool:
    key = (chat_id, message_id)
    if key in SEEN_GROUP_MESSAGES:
        return False
    SEEN_GROUP_MESSAGES.add(key)
    while len(SEEN_GROUP_MESSAGES) > SEEN_LIMIT:
        SEEN_GROUP_MESSAGES.pop()
    return True


def is_source_group(chat_id: int) -> bool:
    if chat_id in INTERNAL_CHAT_IDS:
        return False
    if SOURCE_GROUP_IDS:
        return chat_id in SOURCE_GROUP_IDS
    return True


def public_destinations(source_chat_id: Optional[int] = None) -> list[int]:
    blocked = {CHAT_ID, TRANSPORT_CHAT_ID, 0, None}
    if source_chat_id:
        blocked.add(source_chat_id)

    if REPOST_GROUP_IDS:
        return [gid for gid in REPOST_GROUP_IDS if gid not in blocked]

    targets = [gid for gid in KNOWN_GROUPS if gid not in blocked]
    if targets:
        return targets
    if source_chat_id and source_chat_id not in INTERNAL_CHAT_IDS:
        return [source_chat_id]
    return []


def format_transport_block(listing: Optional[dict[str, Any]], listing_id: str) -> str:
    if not listing:
        if listing_id:
            return (
                "\n\n"
                f"🚛 <b>Відгук на транспорт</b> <code>t_{h(listing_id)}</code>\n"
                "Картку транспорту не знайдено в базі."
            )
        return ""

    username = listing.get("carrier_username") or ""
    username_line = f"@{h(username)}" if username else "Не вказано"
    public_text = (listing.get("public_text") or listing.get("original_text") or "").strip()
    if len(public_text) > 800:
        public_text = public_text[:800] + "…"

    return (
        "\n\n"
        "🚛 <b>ВІДГУК НА ВІЛЬНИЙ ТРАНСПОРТ</b>\n"
        f"🆔 <b>Картка:</b> <code>t_{h(listing.get('id', listing_id))}</code>\n"
        f"📌 <b>Оголошення:</b>\n{h(public_text)}\n\n"
        f"👤 <b>Перевізник:</b> {h(listing.get('carrier_name', '—'))}\n"
        f"📱 <b>Телефон перевізника:</b> {h(listing.get('carrier_phone') or '—')}\n"
        f"💬 <b>Username перевізника:</b> {username_line}\n"
        f"🆔 <b>User ID перевізника:</b> {h(listing.get('carrier_user_id', '—'))}"
    )


def format_cargo_manager_message(data: dict[str, Any], user) -> str:
    username = f"@{user.username}" if user.username else "Не вказано"
    full_name = user.full_name or user.first_name or "—"
    listing_id = data.get("transport_id") or ""
    listing = data.get("transport")
    return (
        "🚚 <b>НОВА ЗАЯВКА НА ПЕРЕВЕЗЕННЯ</b>\n\n"
        f"📦 <b>Товар:</b> {h(data.get('product', ''))}\n"
        f"🌍 <b>Відправлення:</b> {h(data.get('country_from', ''))}\n"
        f"📍 <b>Отримання:</b> {h(data.get('country_to', ''))}\n"
        f"🚛 <b>Тип авто:</b> {h(data.get('vehicle_type', ''))}\n"
        f"📐 <b>Об'єм:</b> {h(data.get('volume', ''))}\n"
        f"⚖️ <b>Вага:</b> {h(data.get('weight', ''))}\n"
        f"🔢 <b>Кількість авто:</b> {h(data.get('vehicle_count', ''))}\n"
        f"💰 <b>Ставка фрахту:</b> {h(data.get('freight_rate', ''))}\n\n"
        f"👤 <b>Замовник:</b> {h(full_name)}\n"
        f"📱 <b>Телефон:</b> {h(data.get('phone', ''))}\n"
        f"💬 <b>Username:</b> {h(username)}\n"
        f"🆔 <b>User ID:</b> {user.id}"
        f"{format_transport_block(listing, listing_id)}"
    )


def public_comment_line(comment: Any) -> str:
    value = str(comment or "").strip()
    if not value or skip_optional(value):
        return ""
    return f"\n💬 <b>Коментар:</b> {h(value)}"


def format_public_form_post(data: dict[str, Any], listing_id: str) -> str:
    return (
        "🚛 <b>ВІЛЬНИЙ ТРАНСПОРТ</b>\n\n"
        f"📍 <b>Місце дислокації:</b> {h(format_place(data.get('country_from', ''), data.get('city_from', '')) or data.get('location', ''))}\n"
        f"🚛 <b>Тип авто:</b> {h(data.get('vehicle_type', ''))}\n"
        f"📐 <b>Об'єм:</b> {h(format_volume(data.get('volume', '')))}\n"
        f"⚖️ <b>Вантажопідйомність:</b> {h(data.get('capacity', ''))} т\n"
        f"🔢 <b>Кількість авто:</b> {h(data.get('vehicle_count', ''))}\n"
        f"🗓 <b>Дата готовності:</b> {h(data.get('ready_date', ''))}\n"
        f"🛣 <b>Напрямок:</b> {h(format_place(data.get('country_to', ''), data.get('city_to', '')) or data.get('direction', ''))}"
        f"{public_comment_line(data.get('comment'))}"
    )


def format_public_group_post(clean_text: str, listing_id: str) -> str:
    return (
        "🚛 <b>ВІЛЬНИЙ ТРАНСПОРТ</b>\n\n"
        f"{h(clean_text)}"
    )


def format_internal_transport_message(
    listing_id: str,
    data: dict[str, Any],
    user,
    source_label: str,
) -> str:
    username = f"@{user.username}" if user.username else "Не вказано"
    full_name = user.full_name or user.first_name or "—"
    extra = ""
    if data.get("location"):
        extra = (
            f"📍 <b>Місце дислокації:</b> {h(format_place(data.get('country_from', ''), data.get('city_from', '')) or data.get('location', ''))}\n"
            f"🚛 <b>Тип авто:</b> {h(data.get('vehicle_type', ''))}\n"
            f"📐 <b>Об'єм:</b> {h(format_volume(data.get('volume', '')))}\n"
            f"⚖️ <b>Вантажопідйомність:</b> {h(data.get('capacity', ''))} т\n"
            f"🔢 <b>Кількість авто:</b> {h(data.get('vehicle_count', ''))}\n"
            f"🗓 <b>Дата готовності:</b> {h(data.get('ready_date', ''))}\n"
            f"🛣 <b>Напрямок:</b> {h(format_place(data.get('country_to', ''), data.get('city_to', '')) or data.get('direction', ''))}\n"
            f"💬 <b>Коментар:</b> {h(data.get('comment', '—'))}\n\n"
        )
    original = data.get("original_text") or ""
    original_block = f"📌 <b>Оголошення:</b>\n{h(original)}\n\n" if original else extra
    return (
        "🚛 <b>НОВИЙ ВІЛЬНИЙ ТРАНСПОРТ</b>\n\n"
        f"🆔 <b>Картка:</b> <code>t_{h(listing_id)}</code>\n"
        f"📥 <b>Джерело:</b> {h(source_label)}\n\n"
        f"{original_block}"
        f"👤 <b>Перевізник:</b> {h(full_name)}\n"
        f"📱 <b>Телефон:</b> {h(data.get('phone', ''))}\n"
        f"💬 <b>Username:</b> {h(username)}\n"
        f"🆔 <b>User ID:</b> {user.id}"
    )


async def send_main_menu(message: Message):
    await message.answer(
        "🚛 Inter Logistics\n\n"
        "Надійно. Вчасно. Професійно.",
        reply_markup=ReplyKeyboardRemove(),
    )


TRANSPORT_INTRO_HTML = (
    "🚛 <b>Маєте вільний транспорт?</b>\n\n"
    "У нас завжди є актуальні вантажі для перевізників!\n\n"
    "Залиште заявку в боті — вкажіть тип авто, напрямок та дату готовності.\n\n"
    "📲 Ми підберемо для вас актуальний вантаж і зв’яжемося з вами в найближчий час!\n\n"
    "Працюємо швидко. Завантажуємо регулярно. Надійно!"
)


async def send_transport_menu(message: Message, *, intro: bool = False) -> None:
    text = TRANSPORT_INTRO_HTML if intro else "Натисніть «Додати авто», щоб залишити заявку."
    await message.answer(
        text,
        reply_markup=transport_menu_keyboard(),
        parse_mode=ParseMode.HTML,
    )


def begin_cargo_state(transport_id: str = "") -> dict[str, Any]:
    listing = get_listing(transport_id) if transport_id else None
    return {
        "funnel": "cargo",
        "step": "product",
        "transport_id": transport_id,
        "transport": listing,
    }


async def start_cargo_funnel(
    message: Message,
    transport_id: str = "",
    user_id: Optional[int] = None,
) -> None:
    uid = user_id or (message.from_user.id if message.from_user else 0)
    if not uid:
        return
    STATE[uid] = begin_cargo_state(transport_id)

    listing = STATE[uid].get("transport")
    intro = "👋 Допоможу залишити заявку на перевезення.\n\n"
    if listing:
        preview = (listing.get("public_text") or "").strip()
        if len(preview) > 280:
            preview = preview[:280] + "…"
        intro = (
            "👋 Бачимо вільний транспорт під ваше направлення.\n\n"
            f"🚛 {preview}\n\n"
            "Залиште заявку на вантаж — менеджер зв'яже вас із перевізником.\n\n"
        )

    await message.answer(
        intro + "📦 Введіть назву товару:",
        reply_markup=ReplyKeyboardRemove(),
    )


async def start_transport_funnel(
    message: Message,
    user_id: Optional[int] = None,
) -> None:
    uid = user_id or (message.from_user.id if message.from_user else 0)
    if not uid:
        return
    STATE[uid] = {"funnel": "transport", "step": "menu"}
    await send_transport_menu(message, intro=True)


async def start_transport_form(
    message: Message,
    user_id: Optional[int] = None,
) -> None:
    uid = user_id or (message.from_user.id if message.from_user else 0)
    if not uid:
        return
    STATE[uid] = {"funnel": "transport", "step": "country_from"}
    await message.answer(
        LOCATION_PROMPT,
        reply_markup=ReplyKeyboardRemove(),
    )


async def start_handler(message: Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
    clear_state(user_id)

    payload_raw = parse_start_payload(message.text or "")
    payload = payload_raw.lower()
    if payload == "transport":
        await start_transport_funnel(message)
        return

    await start_cargo_funnel(
        message,
        transport_id=listing_id_from_payload(payload_raw),
    )


async def notify_managers(bot: Bot, text: str, chat_id: int = CHAT_ID) -> None:
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        log.error("Помилка надсилання менеджерам %s: %s", chat_id, e)


async def save_sheet(**kwargs) -> None:
    try:
        append_row(**kwargs)
    except Exception as e:
        log.error("Помилка збереження в Google Sheets: %s", e)


async def publish_public_listing(
    bot: Bot,
    listing_id: str,
    public_html: str,
    source_chat_id: Optional[int] = None,
    photo_id: Optional[str] = None,
) -> None:
    destinations = public_destinations(source_chat_id)
    if not destinations:
        log.warning("Немає групи для публічного репосту картки %s", listing_id)
        return

    for chat_id in destinations:
        try:
            if photo_id:
                caption = public_html if len(public_html) <= 1024 else public_html[:1020] + "…"
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=public_listing_keyboard(listing_id),
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=public_html,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=public_listing_keyboard(listing_id),
                )
            log.info("Публічний транспорт %s надіслано в %s", listing_id, chat_id)
        except Exception as e:
            log.error("Помилка публікації транспорту %s в %s: %s", listing_id, chat_id, e)


async def finalize_cargo(message: Message, phone: str) -> None:
    user = message.from_user
    user_id = user.id
    state = STATE.get(user_id, {})
    state["phone"] = phone

    listing_id = state.get("transport_id") or ""
    manager_chat = TRANSPORT_CHAT_ID if listing_id else CHAT_ID
    await notify_managers(
        message.bot,
        format_cargo_manager_message(state, user),
        chat_id=manager_chat,
    )
    answers_text = (
        f"Товар: {state.get('product', '')}; "
        f"З: {state.get('country_from', '')}; "
        f"До: {state.get('country_to', '')}; "
        f"Тип авто: {state.get('vehicle_type', '')}; "
        f"Об'єм: {state.get('volume', '')}; "
        f"Вага: {state.get('weight', '')}; "
        f"К-сть авто: {state.get('vehicle_count', '')}; "
        f"Ставка: {state.get('freight_rate', '')}"
    )
    contact_method = "Заявка на перевезення"
    if listing_id:
        answers_text += f"; Відгук на транспорт: t_{listing_id}"
        contact_method = f"Відгук на транспорт t_{listing_id}"

    await save_sheet(
        date_str=now_kyiv_str(),
        name=user.full_name or user.first_name or "—",
        username=user.username,
        phone=phone,
        answers=answers_text,
        tag="logistics",
        contact_method=contact_method,
    )

    clear_state(user_id)
    await message.answer(
        "Дякуємо! Заявку отримано ✅\n\n"
        "Наш менеджер зв'яжеться з вами найближчим часом та уточнить усі деталі перевезення.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await send_main_menu(message)


async def finalize_transport(message: Message, phone: str) -> None:
    user = message.from_user
    user_id = user.id
    state = STATE.get(user_id, {})
    state["phone"] = phone

    from_place = format_place(state.get("country_from", ""), state.get("city_from", ""))
    to_place = format_place(state.get("country_to", ""), state.get("city_to", ""))
    state["location"] = from_place
    state["direction"] = to_place
    public_text = (
        f"Дислокація: {from_place}\n"
        f"Тип авто: {state.get('vehicle_type', '')}\n"
        f"Об'єм: {format_volume(state.get('volume', ''))}\n"
        f"Вантажопідйомність: {state.get('capacity', '')} т\n"
        f"Кількість авто: {state.get('vehicle_count', '')}\n"
        f"Дата готовності: {state.get('ready_date', '')}\n"
        f"Напрямок: {to_place}"
    )
    comment = (state.get("comment") or "").strip()
    if comment and not skip_optional(comment):
        public_text += f"\nКоментар: {comment}"
    listing_id = save_listing(
        {
            "source": "bot_form",
            "public_text": public_text,
            "original_text": public_text,
            "location": state.get("location", ""),
            "vehicle_type": state.get("vehicle_type", ""),
            "direction": state.get("direction", ""),
            "carrier_name": user.full_name or user.first_name or "—",
            "carrier_username": user.username or "",
            "carrier_user_id": user.id,
            "carrier_phone": phone,
        }
    )

    await publish_public_listing(
        message.bot,
        listing_id,
            format_public_form_post(state, listing_id),
    )
    await notify_managers(
        message.bot,
        format_internal_transport_message(listing_id, state, user, "воронка бота"),
        chat_id=TRANSPORT_CHAT_ID,
    )
    await save_sheet(
        date_str=now_kyiv_str(),
        name=user.full_name or user.first_name or "—",
        username=user.username,
        phone=phone,
        answers=(
            f"ID: t_{listing_id}; "
            f"Дислокація: {from_place}; "
            f"Тип авто: {state.get('vehicle_type', '')}; "
            f"Об'єм: {format_volume(state.get('volume', ''))}; "
            f"Вантажопідйомність: {state.get('capacity', '')} т; "
            f"К-сть авто: {state.get('vehicle_count', '')}; "
            f"Дата готовності: {state.get('ready_date', '')}; "
            f"Напрямок: {to_place}; "
            f"Коментар: {state.get('comment', '—')}"
        ),
        tag="transport",
        contact_method="Вільний транспорт",
    )

    clear_state(user_id)
    STATE[user_id] = {"funnel": "transport", "step": "menu"}
    await message.answer(
        "Дякуємо! Ваш транспорт зареєстровано ✅\n\n"
        "Наші логісти вже підбирають вантаж для вашого авто. "
        "Очікуйте на зворотний зв'язок!",
        reply_markup=transport_menu_keyboard(),
    )


async def handle_group_transport(message: Message):
    if message.chat.id not in INTERNAL_CHAT_IDS:
        remember_group(message.chat.id)

    if not message.from_user or message.from_user.is_bot:
        return
    if not is_source_group(message.chat.id):
        return
    if not remember_message(message.chat.id, message.message_id):
        return

    raw_text = (message.text or message.caption or "").strip()
    if not raw_text or looks_like_our_repost(raw_text) or raw_text.startswith("/"):
        return
    if not is_free_transport(raw_text):
        return

    clean_text = strip_contacts(raw_text)
    if len(clean_text) < 12:
        return

    user = message.from_user
    phones = extract_phones(raw_text)
    listing_id = save_listing(
        {
            "source": "group",
            "public_text": clean_text,
            "original_text": raw_text,
            "carrier_name": user.full_name or user.first_name or "—",
            "carrier_username": user.username or "",
            "carrier_user_id": user.id,
            "carrier_phone": phones,
            "source_chat_id": message.chat.id,
            "source_chat_title": message.chat.title or "",
            "source_message_id": message.message_id,
        }
    )

    photo_id = message.photo[-1].file_id if message.photo else None
    await publish_public_listing(
        message.bot,
        listing_id,
        format_public_group_post(clean_text, listing_id),
        source_chat_id=message.chat.id,
        photo_id=photo_id,
    )

    source_label = message.chat.title or str(message.chat.id)
    await notify_managers(
        message.bot,
        format_internal_transport_message(
            listing_id,
            {"original_text": raw_text, "phone": phones or "з групи"},
            user,
            f"група {source_label}",
        ),
        chat_id=TRANSPORT_CHAT_ID,
    )
    await save_sheet(
        date_str=now_kyiv_str(),
        name=user.full_name or user.first_name or "—",
        username=user.username,
        phone=phones or "з групи",
        answers=f"ID: t_{listing_id}; Група: {source_label}; Текст: {raw_text}",
        tag="transport_group",
        contact_method="Вільний транспорт з групи",
    )


async def handle_cargo_flow(message: Message, state: dict[str, Any]) -> None:
    text = (message.text or "").strip()
    step = state.get("step")

    if step == "product":
        if not text:
            await message.answer("📦 Введіть назву товару:")
            return
        state["product"] = text
        state["step"] = "country_from"
        await message.answer(CARGO_FROM_PROMPT)
        return

    if step == "country_from":
        if not text:
            await message.answer(CARGO_FROM_PROMPT)
            return
        state["country_from"] = text
        state["step"] = "country_to"
        await message.answer(CARGO_TO_PROMPT)
        return

    if step == "country_to":
        if not text:
            await message.answer(CARGO_TO_PROMPT)
            return
        state["country_to"] = text
        state["step"] = "vehicle_type"
        await message.answer("🚛 Оберіть тип авто:", reply_markup=vehicle_keyboard(CARGO_VEHICLE_TYPES))
        return

    if step == "vehicle_type":
        if text == "Інше":
            state["step"] = "vehicle_type_custom"
            await message.answer(
                "🚛 Введіть тип авто вручну:",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        if text not in CARGO_VEHICLE_TYPES:
            await message.answer(
                "🚛 Оберіть тип авто з кнопок нижче або натисніть «Інше»:",
                reply_markup=vehicle_keyboard(CARGO_VEHICLE_TYPES),
            )
            return
        state["vehicle_type"] = text
        if text == "Цистерна":
            state["step"] = "volume"
            await message.answer("📐 Введіть об'єм (м³):", reply_markup=ReplyKeyboardRemove())
        else:
            state["volume"] = "—"
            state["step"] = "weight"
            await message.answer("⚖️ Введіть вагу (тонн):", reply_markup=ReplyKeyboardRemove())
        return

    if step == "vehicle_type_custom":
        if not text:
            await message.answer("🚛 Введіть тип авто вручну:")
            return
        state["vehicle_type"] = text
        state["volume"] = "—"
        state["step"] = "weight"
        await message.answer("⚖️ Введіть вагу (тонн):")
        return

    if step == "volume":
        if not text:
            await message.answer("📐 Введіть об'єм (м³):")
            return
        state["volume"] = text
        state["step"] = "weight"
        await message.answer("⚖️ Введіть вагу (тонн):")
        return

    if step == "weight":
        if not text:
            await message.answer("⚖️ Введіть вагу (тонн):")
            return
        state["weight"] = text
        state["step"] = "vehicle_count"
        await message.answer("🔢 Введіть кількість авто:")
        return

    if step == "vehicle_count":
        if not text:
            await message.answer("🔢 Введіть кількість авто:")
            return
        state["vehicle_count"] = text
        state["step"] = "freight_rate"
        await message.answer(
            "💰 Введіть бажану ставку фрахту (або напишіть «за домовленістю»):"
        )
        return

    if step == "freight_rate":
        if not text:
            await message.answer(
                "💰 Введіть бажану ставку фрахту (або напишіть «за домовленістю»):"
            )
            return
        state["freight_rate"] = text
        state["step"] = "phone"
        await message.answer(
            "📞 Надішліть ваш номер телефону для зворотного зв'язку:\n\n"
            "Натисніть кнопку нижче або введіть номер вручну.",
            reply_markup=phone_keyboard(),
        )
        return

    if step == "phone":
        if message.contact and message.contact.phone_number:
            phone = message.contact.phone_number
        elif text:
            phone = text
        else:
            await message.answer(
                "📞 Надішліть номер телефону кнопкою або текстом.",
                reply_markup=phone_keyboard(),
            )
            return
        await finalize_cargo(message, phone)
        return

    await send_main_menu(message)


async def handle_transport_flow(message: Message, state: dict[str, Any]) -> None:
    text = (message.text or "").strip()
    step = state.get("step")

    if text == ADD_VEHICLE_BUTTON:
        await start_transport_form(message)
        return

    if step == "menu":
        await send_transport_menu(message)
        return

    if step == "country_from":
        if not text:
            await message.answer(LOCATION_PROMPT)
            return
        state["country_from"] = text
        state["location"] = text
        state["step"] = "vehicle_type"
        await message.answer("🚛 Оберіть тип авто:", reply_markup=vehicle_keyboard(TRANSPORT_VEHICLE_TYPES))
        return

    if step == "vehicle_type":
        if text == "Інше":
            state["step"] = "vehicle_type_custom"
            await message.answer(
                "🚛 Введіть тип авто вручну:",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        if text not in TRANSPORT_VEHICLE_TYPES:
            await message.answer(
                "🚛 Оберіть тип авто з кнопок нижче або натисніть «Інше»:",
                reply_markup=vehicle_keyboard(TRANSPORT_VEHICLE_TYPES),
            )
            return
        state["vehicle_type"] = text
        state["step"] = "volume"
        await message.answer(
            "📐 Введіть об'єм кузова (м³) або «-» якщо не вказувати:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if step == "vehicle_type_custom":
        if not text:
            await message.answer("🚛 Введіть тип авто вручну:")
            return
        state["vehicle_type"] = text
        state["step"] = "volume"
        await message.answer("📐 Введіть об'єм кузова (м³) або «-» якщо не вказувати:")
        return

    if step == "volume":
        if not text:
            await message.answer("📐 Введіть об'єм кузова (м³) або «-» якщо не вказувати:")
            return
        state["volume"] = "—" if skip_optional(text) else text
        state["step"] = "capacity"
        await message.answer("⚖️ Введіть вантажопідйомність (тонн):")
        return

    if step == "capacity":
        if not text:
            await message.answer("⚖️ Введіть вантажопідйомність (тонн):")
            return
        state["capacity"] = text
        state["step"] = "vehicle_count"
        await message.answer("🔢 Введіть кількість вільних авто:")
        return

    if step == "vehicle_count":
        if not text:
            await message.answer("🔢 Введіть кількість вільних авто:")
            return
        state["vehicle_count"] = text
        state["step"] = "ready_date"
        await message.answer("🗓 Вкажіть дату готовності (наприклад: 05.09.2026 або «зараз»):")
        return

    if step == "ready_date":
        if not text:
            await message.answer("🗓 Вкажіть дату готовності:")
            return
        state["ready_date"] = text
        state["step"] = "country_to"
        await message.answer(DIRECTION_PROMPT)
        return

    if step == "country_to":
        if not text:
            await message.answer(DIRECTION_PROMPT)
            return
        state["country_to"] = text
        state["direction"] = text
        state["step"] = "comment"
        await message.answer("💬 Додатковий коментар (або напишіть «—» щоб пропустити):")
        return

    if step == "comment":
        if not text:
            await message.answer("💬 Додатковий коментар (або «—»):")
            return
        state["comment"] = "—" if skip_optional(text) else text
        state["step"] = "phone"
        await message.answer(
            "📞 Надішліть ваш номер телефону для зворотного зв'язку:\n\n"
            "Натисніть кнопку нижче або введіть номер вручну.",
            reply_markup=phone_keyboard(),
        )
        return

    if step == "phone":
        if message.contact and message.contact.phone_number:
            phone = message.contact.phone_number
        elif text:
            phone = text
        else:
            await message.answer(
                "📞 Надішліть номер телефону кнопкою або текстом.",
                reply_markup=phone_keyboard(),
            )
            return
        await finalize_transport(message, phone)
        return

    await send_transport_menu(message)


async def handle_private_message(message: Message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id
    text = (message.text or "").strip()
    state = STATE.get(user_id)
    if text == ADD_VEHICLE_BUTTON and (not state or state.get("funnel") == "transport"):
        await start_transport_form(message)
        return
    if not state:
        await send_main_menu(message)
        return

    if state.get("funnel") == "transport":
        await handle_transport_flow(message, state)
        return
    await handle_cargo_flow(message, state)


async def add_vehicle_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not callback.message:
        return
    await start_transport_form(callback.message, user_id=callback.from_user.id)


async def test_push_handler(message: Message):
    await message.answer("⏳ Відправляю тестовий пуш в канал...")
    await send_channel_push(message.bot)
    await message.answer("✅ Готово! Перевір канал.")


async def post_transport_promo_handler(message: Message):
    if message.chat.type == "private":
        await message.answer(
            "Надішліть /promo в групу або канал, де треба закріпити пост із кнопкою."
        )
        return

    sent = await message.bot.send_message(
        chat_id=message.chat.id,
        text=TRANSPORT_INTRO_HTML,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=transport_url_keyboard(),
    )
    try:
        await message.bot.pin_chat_message(
            chat_id=message.chat.id,
            message_id=sent.message_id,
            disable_notification=True,
        )
    except Exception as e:
        log.warning("Не вдалося закріпити промо в %s: %s", message.chat.id, e)


async def main():
    bot = Bot(token=BOT_TOKEN, session=RetryingSession(timeout=90.0))
    dp = Dispatcher()

    asyncio.create_task(channel_push_scheduler(bot))

    dp.message.register(start_handler, CommandStart())
    dp.callback_query.register(add_vehicle_callback, F.data == "add_vehicle")
    dp.message.register(test_push_handler, Command("testpush"))
    dp.message.register(post_transport_promo_handler, Command("promo"))
    dp.channel_post.register(post_transport_promo_handler, Command("promo"))
    dp.message.register(handle_group_transport, F.chat.type.in_({"group", "supergroup"}))
    dp.message.register(handle_private_message)

    log.info("Inter Logistics Bot started as @%s", BOT_USERNAME)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
