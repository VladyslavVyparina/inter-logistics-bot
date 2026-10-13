import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import BOT_USERNAME, CHANNEL_ID, TRANSPORT_CHANNEL_ID, TRANSPORT_PUSH_EXTRA_CHAT_ID

log = logging.getLogger(__name__)

KYIV_TZ = ZoneInfo("Europe/Kyiv")

PUSH_WEEKDAYS = {0, 1, 2, 3, 4}
PUSH_SLOTS = {(10, 30), (14, 0), (16, 0)}

PUSH_TEXT = (
    "🚛 Потрібно перевезти вантаж?\n\n"
    "Заповніть коротку заявку — наша компанія організує перевезення "
    "від завантаження до доставки.\n\n"
    "Надійно. Вчасно. Професійно."
)


TRANSPORT_PUSH_TEXT = (
    "🚛 <b>Маєте вільний транспорт?</b>\n\n"
    "У нас завжди є актуальні вантажі для перевізників!\n\n"
    "Залиште заявку в боті — вкажіть тип авто, напрямок та дату готовності.\n\n"
    "📲 Ми підберемо для вас актуальний вантаж і зв’яжемося з вами в найближчий час!\n\n"
    "Працюємо швидко. Завантажуємо регулярно. Надійно!"
)


def cargo_push_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👉 Заповнити заявку",
                    url=f"https://t.me/{BOT_USERNAME}?start=logistics",
                )
            ]
        ]
    )


def transport_push_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Додати авто",
                    url=f"https://t.me/{BOT_USERNAME}?start=transport",
                )
            ]
        ]
    )


async def send_channel_push(bot: Bot) -> None:
    if not CHANNEL_ID:
        log.warning("CHANNEL_ID не встановлено, пуш не відправлено")
        return

    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=PUSH_TEXT,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=cargo_push_keyboard(),
        )
        log.info("Пуш-повідомлення відправлено в канал %s", CHANNEL_ID)
    except Exception as e:
        log.error("Помилка відправки пушу в канал: %s", e)


async def send_transport_push(bot: Bot) -> None:
    targets = [cid for cid in (TRANSPORT_CHANNEL_ID, TRANSPORT_PUSH_EXTRA_CHAT_ID) if cid]
    if not targets:
        log.warning("Немає каналів для транспортного пушу")
        return

    for chat_id in targets:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=TRANSPORT_PUSH_TEXT,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=transport_push_keyboard(),
            )
            log.info("Транспортний пуш відправлено в канал %s", chat_id)
        except Exception as e:
            log.error("Помилка відправки транспортного пушу в канал %s: %s", chat_id, e)


async def channel_push_scheduler(bot: Bot) -> None:
    log.info("Планувальник пушів запущено")

    while True:
        now = datetime.now(KYIV_TZ)

        if now.weekday() in PUSH_WEEKDAYS and (now.hour, now.minute) in PUSH_SLOTS:
            await send_channel_push(bot)
            await send_transport_push(bot)
            await asyncio.sleep(61)
        else:
            await asyncio.sleep(30)
