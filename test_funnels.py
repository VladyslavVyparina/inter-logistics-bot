#!/usr/bin/env python3
"""Локальна перевірка двох воронок без живого Telegram API."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import listings as listings_mod
import bot as botmod
from text_utils import (
    extract_phones,
    is_free_transport,
    looks_like_our_repost,
    strip_contacts,
)


class FakeUser:
    def __init__(self, user_id: int, username: str = "user", name: str = "Тест"):
        self.id = user_id
        self.username = username
        self.full_name = name
        self.first_name = name
        self.is_bot = False


class FakeChat:
    def __init__(self, chat_type: str = "private", chat_id: int = 111, title: str = ""):
        self.type = chat_type
        self.id = chat_id
        self.title = title


class FakeMessage:
    def __init__(self, text: str, user: FakeUser, chat: FakeChat | None = None, contact=None):
        self.text = text
        self.from_user = user
        self.chat = chat or FakeChat()
        self.contact = contact
        self.caption = None
        self.photo = None
        self.message_id = 1
        self.bot = SimpleNamespace()
        self.answers: list[str] = []
        self.last_markup = None

    async def answer(self, text: str, reply_markup=None, **kwargs):
        self.answers.append(text)
        self.last_markup = reply_markup
        return self

    async def edit_reply_markup(self, reply_markup=None):
        self.last_markup = reply_markup


def route_of(text: str) -> str:
    payload = botmod.parse_start_payload(text).lower()
    listing_id = botmod.listing_id_from_payload(botmod.parse_start_payload(text))
    if payload == "transport":
        return "transport"
    return "cargo"


class FunnelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        listings_mod.LISTINGS_PATH = str(Path(self._tmp.name) / "listings.json")
        botmod.STATE.clear()
        botmod.KNOWN_GROUPS.clear()
        botmod.SEEN_GROUP_MESSAGES.clear()
        self.manager: list[str] = []
        self.sheet: list[dict] = []
        self.public: list[tuple] = []

        async def fake_notify(bot, text, chat_id=None):
            self.manager.append(text)

        async def fake_sheet(**kwargs):
            self.sheet.append(kwargs)

        async def fake_publish(bot, listing_id, public_html, source_chat_id=None, photo_id=None):
            self.public.append(
                {
                    "listing_id": listing_id,
                    "html": public_html,
                    "source_chat_id": source_chat_id,
                    "keyboard": botmod.public_listing_keyboard(listing_id),
                }
            )

        botmod.notify_managers = fake_notify
        botmod.save_sheet = fake_sheet
        botmod.publish_public_listing = fake_publish

    def tearDown(self):
        self._tmp.cleanup()

    def test_start_links_do_not_mix(self):
        self.assertEqual(route_of("/start"), "cargo")
        self.assertEqual(route_of("/start logistics"), "cargo")
        self.assertEqual(route_of("/start LOGISTICS"), "cargo")
        self.assertEqual(route_of("/start transport"), "transport")
        self.assertEqual(route_of("/start TRANSPORT"), "transport")
        self.assertEqual(route_of("/start t_ab12cd34"), "cargo")
        self.assertNotEqual(route_of("/start transport"), "cargo")
        self.assertNotEqual(route_of("/start logistics"), "transport")
        self.assertEqual(botmod.listing_id_from_payload("transport"), "")
        self.assertEqual(botmod.listing_id_from_payload("t_ab12cd34"), "ab12cd34")

    async def test_cargo_funnel_full_path(self):
        user = FakeUser(1, "cargo_user", "Замовник")
        msg = FakeMessage("/start logistics", user)
        await botmod.start_handler(msg)
        self.assertEqual(botmod.STATE[1]["funnel"], "cargo")
        self.assertIn("назву товару", msg.answers[-1])

        product_msg = FakeMessage("Меблі", user)
        await botmod.handle_private_message(product_msg)
        self.assertIn("відправлення", product_msg.answers[-1])
        self.assertNotIn("дислокації", product_msg.answers[-1])
        self.assertNotIn("готові їхати", product_msg.answers[-1])

        answers = [
            "Польща, Варшава",
            "Україна, Київ",
            "Тент",
            "22",
            "1",
            "1200€",
            "+380501112233",
        ]
        for text in answers:
            step_msg = FakeMessage(text, user)
            await botmod.handle_private_message(step_msg)

        self.assertNotIn(1, botmod.STATE)
        self.assertEqual(len(self.manager), 1)
        self.assertIn("НОВА ЗАЯВКА НА ПЕРЕВЕЗЕННЯ", self.manager[0])
        self.assertIn("Польща, Варшава", self.manager[0])
        self.assertIn("Україна, Київ", self.manager[0])
        self.assertIn("Замовник", self.manager[0])
        self.assertNotIn("Місце дислокації", self.manager[0])
        self.assertEqual(self.sheet[0]["tag"], "logistics")
        self.assertEqual(self.sheet[0]["contact_method"], "Заявка на перевезення")
        self.assertEqual(self.public, [])

    async def test_transport_funnel_full_path(self):
        user = FakeUser(2, "carrier", "Перевізник")
        msg = FakeMessage("/start transport", user)
        await botmod.start_handler(msg)
        self.assertEqual(botmod.STATE[2]["funnel"], "transport")
        self.assertEqual(botmod.STATE[2]["step"], "menu")
        self.assertIn("вільний транспорт", msg.answers[-1].lower())
        self.assertNotIn("Введіть країну", msg.answers[-1])
        self.assertEqual(msg.last_markup.inline_keyboard[0][0].text, "Додати авто")
        self.assertEqual(msg.last_markup.inline_keyboard[0][0].callback_data, "add_vehicle")

        await botmod.handle_private_message(FakeMessage("Додати авто", user))
        self.assertEqual(botmod.STATE[2]["step"], "country_from")

        answers = [
            "Греція, Афіни",
            "Тент",
            "90",
            "22",
            "1",
            "зараз",
            "Україна, Київ",
            "готовий сьогодні",
            "+380509998877",
        ]
        for text in answers:
            step_msg = FakeMessage(text, user)
            await botmod.handle_private_message(step_msg)

        self.assertEqual(botmod.STATE[2]["step"], "menu")
        self.assertEqual(len(self.manager), 1)
        self.assertIn("НОВИЙ ВІЛЬНИЙ ТРАНСПОРТ", self.manager[0])
        self.assertIn("Греція", self.manager[0])
        self.assertIn("Перевізник", self.manager[0])
        self.assertNotIn("НОВА ЗАЯВКА НА ПЕРЕВЕЗЕННЯ", self.manager[0])
        self.assertEqual(self.sheet[0]["tag"], "transport")
        self.assertEqual(len(self.public), 1)
        self.assertIn("готовий сьогодні", self.public[0]["html"])
        self.assertIn("Коментар", self.public[0]["html"])
        self.assertNotIn("Залишити заявку", self.public[0]["html"])
        self.assertNotIn("━━━━━━━━", self.public[0]["html"])
        self.assertNotIn("🇺🇦", self.public[0]["html"])
        self.assertIn("🛣", self.public[0]["html"])
        self.assertNotIn("🇺🇦", self.manager[0])
        self.assertIn("🛣", self.manager[0])
        self.assertNotIn("━━━━━━━━", self.manager[0])
        self.assertNotIn("+380509998877", self.public[0]["html"])
        button = self.public[0]["keyboard"].inline_keyboard[0][0]
        self.assertEqual(button.text, "Додати вантаж")
        self.assertIn("start=t_", button.url)
        self.assertIn("+380509998877", self.manager[0])

    async def test_transport_accepts_typed_place_without_buttons(self):
        user = FakeUser(21, "carrier2", "Перевізник")
        msg = FakeMessage("/start transport", user)
        await botmod.start_handler(msg)
        self.assertEqual(botmod.STATE[21]["step"], "menu")
        self.assertIn("вільний транспорт", msg.answers[-1].lower())
        self.assertNotIn("Оберіть країну", msg.answers[-1])

        await botmod.handle_private_message(FakeMessage("Додати авто", user))
        self.assertEqual(botmod.STATE[21]["step"], "country_from")

        step_msg = FakeMessage("Украина, Киев", user)
        await botmod.handle_private_message(step_msg)
        self.assertEqual(botmod.STATE[21]["country_from"], "Украина, Киев")
        self.assertEqual(botmod.STATE[21]["step"], "vehicle_type")
        self.assertIn("тип авто", step_msg.answers[-1].lower())

    async def test_two_users_do_not_mix_state(self):
        cargo_user = FakeUser(10, "c", "Карго")
        truck_user = FakeUser(20, "t", "Трак")
        await botmod.start_handler(FakeMessage("/start logistics", cargo_user))
        await botmod.start_handler(FakeMessage("/start transport", truck_user))
        self.assertEqual(botmod.STATE[10]["funnel"], "cargo")
        self.assertEqual(botmod.STATE[20]["funnel"], "transport")

        await botmod.handle_private_message(FakeMessage("Плитка", cargo_user))
        await botmod.handle_private_message(FakeMessage("Додати авто", truck_user))
        await botmod.handle_private_message(FakeMessage("Греція, Афіни", truck_user))
        self.assertEqual(botmod.STATE[10]["product"], "Плитка")
        self.assertEqual(botmod.STATE[10]["step"], "country_from")
        self.assertEqual(botmod.STATE[20]["country_from"], "Греція, Афіни")
        self.assertEqual(botmod.STATE[20]["step"], "vehicle_type")
        self.assertNotIn("location", botmod.STATE[10])
        self.assertNotIn("product", botmod.STATE[20])

    async def test_transport_menu_waits_for_add_button(self):
        user = FakeUser(22, "carrier3", "Перевізник")
        await botmod.start_handler(FakeMessage("/start transport", user))
        await botmod.handle_private_message(FakeMessage("Украина, Киев", user))
        self.assertEqual(botmod.STATE[22]["step"], "menu")
        self.assertNotIn("country_from", botmod.STATE[22])

        await botmod.handle_private_message(FakeMessage("Додати авто", user))
        self.assertEqual(botmod.STATE[22]["step"], "country_from")

    async def test_add_vehicle_inline_callback_starts_form(self):
        user = FakeUser(30, "carrier4", "Перевізник")
        msg = FakeMessage("/start transport", user)
        await botmod.start_handler(msg)

        class FakeCallback:
            def __init__(self):
                self.from_user = user
                self.message = msg
                self.data = "add_vehicle"

            async def answer(self):
                return None

        await botmod.add_vehicle_callback(FakeCallback())
        self.assertEqual(botmod.STATE[30]["step"], "country_from")
        self.assertIn("дислокації", msg.answers[-1])

    async def test_deep_link_binds_cargo_to_transport(self):
        listing_id = listings_mod.save_listing(
            {
                "public_text": "Тент 13.6 Греція - Київ",
                "carrier_name": "Іван Перевізник",
                "carrier_username": "ivan_truck",
                "carrier_user_id": 777,
                "carrier_phone": "+306911111111",
            }
        )
        user = FakeUser(3, "shipper", "Замовник Вантажу")
        await botmod.start_handler(FakeMessage(f"/start t_{listing_id}", user))
        self.assertEqual(botmod.STATE[3]["funnel"], "cargo")
        self.assertNotEqual(botmod.STATE[3]["funnel"], "transport")
        self.assertEqual(botmod.STATE[3]["transport_id"], listing_id)
        self.assertEqual(botmod.STATE[3]["step"], "product")
        self.assertEqual(botmod.STATE[3]["transport"]["carrier_name"], "Іван Перевізник")

        for text in [
            "Автозапчастини",
            "Греція, Афіни",
            "Україна, Київ",
            "Тент",
            "20",
            "1",
            "договірна",
            "380501110000",
        ]:
            await botmod.handle_private_message(FakeMessage(text, user))

        self.assertIn("ВІДГУК НА ВІЛЬНИЙ ТРАНСПОРТ", self.manager[0])
        self.assertIn("Іван Перевізник", self.manager[0])
        self.assertIn("+306911111111", self.manager[0])
        self.assertIn("Замовник Вантажу", self.manager[0])
        self.assertIn("Автозапчастини", self.manager[0])
        self.assertEqual(self.sheet[0]["contact_method"], f"Відгук на транспорт t_{listing_id}")

    def test_group_text_detection_and_contact_strip(self):
        transport_post = (
            "Вільний транспорт тент 13.6\n"
            "Греція - Україна, Київ\n"
            "тел +30 691 123 4567 @driver_nick https://t.me/driver_nick"
        )
        cargo_post = "Є вантаж плитка Польща-Київ, шукаю машину, тел +380501112233"
        self.assertTrue(is_free_transport(transport_post))
        self.assertFalse(is_free_transport(cargo_post))
        cleaned = strip_contacts(transport_post)
        self.assertNotIn("+30", cleaned)
        self.assertNotIn("@driver_nick", cleaned)
        self.assertNotIn("t.me/driver_nick", cleaned)
        self.assertIn("Греція", cleaned)
        self.assertIn("+306911234567", extract_phones(transport_post).replace(" ", "").replace("-", "") or extract_phones(transport_post))
        self.assertTrue(extract_phones(transport_post))
        self.assertTrue(looks_like_our_repost("🚛 ВІЛЬНИЙ ТРАНСПОРТ\nМісце дислокації: Київ"))
        self.assertTrue(looks_like_our_repost("🚛 ВІЛЬНИЙ ТРАНСПОРТ\nЗалишити заявку"))
        self.assertFalse(looks_like_our_repost(transport_post))

    def test_two_separate_funnel_links(self):
        self.assertEqual(
            botmod.cargo_funnel_url(),
            "https://t.me/Inter_Logisticss_bot?start=logistics",
        )
        self.assertEqual(
            botmod.transport_funnel_url(),
            "https://t.me/Inter_Logisticss_bot?start=transport",
        )
        self.assertEqual(
            botmod.cargo_funnel_url("ab12cd34"),
            "https://t.me/Inter_Logisticss_bot?start=t_ab12cd34",
        )
        self.assertNotIn("transport", botmod.cargo_funnel_url())
        self.assertNotIn("logistics", botmod.transport_funnel_url())

    def test_source_group_skips_manager_chat(self):
        self.assertFalse(botmod.is_source_group(botmod.CHAT_ID))
        self.assertFalse(botmod.is_source_group(botmod.TRANSPORT_CHAT_ID))
        self.assertFalse(botmod.is_source_group(botmod.CHANNEL_ID))
        self.assertFalse(botmod.is_source_group(botmod.TRANSPORT_CHANNEL_ID))
        self.assertFalse(botmod.is_source_group(botmod.TRANSPORT_PUSH_EXTRA_CHAT_ID))
        self.assertTrue(botmod.is_source_group(-1001111111111))
        self.assertEqual(botmod.public_destinations(), [botmod.CHANNEL_ID])
        self.assertNotIn(botmod.TRANSPORT_CHANNEL_ID, botmod.public_destinations())

    def test_vehicle_types_differ_by_funnel(self):
        self.assertIn("Контейнер", botmod.CARGO_VEHICLE_TYPES)
        self.assertNotIn("Контейнеровіз", botmod.CARGO_VEHICLE_TYPES)
        self.assertIn("Контейнеровіз", botmod.TRANSPORT_VEHICLE_TYPES)
        self.assertNotIn("Контейнер", botmod.TRANSPORT_VEHICLE_TYPES)

    def test_cargo_push_times(self):
        import scheduler as sched
        self.assertEqual(sched.PUSH_SLOTS, {(10, 30), (14, 0), (16, 0)})
        self.assertEqual(sched.TRANSPORT_CHANNEL_ID, -1002031991424)
        self.assertEqual(sched.TRANSPORT_PUSH_EXTRA_CHAT_ID, -1004349240981)
        self.assertIn("Маєте вільний транспорт", sched.TRANSPORT_PUSH_TEXT)
        self.assertEqual(
            sched.transport_push_keyboard().inline_keyboard[0][0].text,
            "Додати авто",
        )


if __name__ == "__main__":
    unittest.main()
