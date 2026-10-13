import os

BOT_TOKEN = "8638327471:AAGi0AHTIOnP825BvshDcmycCxmjZyJ9TEc"

# Username бота без @
BOT_USERNAME = "Inter_Logisticss_bot"

# Чат менеджерів по вантажу (стара воронка)
CHAT_ID = -1004405977967

# Чат менеджерів по вільному транспорту (нова воронка)
TRANSPORT_CHAT_ID = -1004365839600

# Канал для вантажних пушів і карток «ВІЛЬНИЙ ТРАНСПОРТ» (кнопка «Додати вантаж»)
CHANNEL_ID = -1002120477749

# Канал, де залишають заявки на авто (кнопка «Додати авто»). Картки сюди не публікуємо.
TRANSPORT_CHANNEL_ID = -1002031991424

# Другий канал для того самого транспортного пуша (ретранслятор його не копіює).
TRANSPORT_PUSH_EXTRA_CHAT_ID = -1004349240981

# Групи, звідки ловимо вільний транспорт.
# Порожній список = усі групи, куди додано бота (крім чату менеджерів і каналу).
SOURCE_GROUP_IDS = []

# Картки вільного транспорту з кнопкою «Додати вантаж» — лише сюди.
REPOST_GROUP_IDS = [-1002120477749]

# Google Sheets — та сама таблиця
GOOGLE_SHEET_ID = "1Z_H5i_Fore1IuVz2lR49NDe7A-dVpiORtwtyfKvN1J8"
GOOGLE_SHEET_RANGE = "B:H"

LISTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "listings.json")
