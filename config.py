import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Bot username without @
BOT_USERNAME = os.environ.get("BOT_USERNAME", "Inter_Logisticss_bot")

# Manager chat for freight requests (the original funnel)
CHAT_ID = int(os.environ.get("CHAT_ID", "-1004405977967"))

# Manager chat for free-transport listings (the later funnel)
TRANSPORT_CHAT_ID = int(os.environ.get("TRANSPORT_CHAT_ID", "-1004365839600"))

# Channel for freight pushes and "free transport" cards (the Add cargo button)
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1002120477749"))

# Channel where vehicle requests are left (the Add vehicle button). Cards are not posted here.
TRANSPORT_CHANNEL_ID = int(os.environ.get("TRANSPORT_CHANNEL_ID", "-1002031991424"))

# Second channel for the same transport push. The relay does not copy it.
TRANSPORT_PUSH_EXTRA_CHAT_ID = int(os.environ.get("TRANSPORT_PUSH_EXTRA_CHAT_ID", "-1004349240981"))

# Groups the bot watches for free transport.
# An empty list means every group the bot is in, except the manager chat and the channel.
SOURCE_GROUP_IDS = []

# Free-transport cards with the Add cargo button go only here.
REPOST_GROUP_IDS = [CHANNEL_ID]

# Google Sheets — the same spreadsheet as the working copy
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_RANGE = "B:H"

LISTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "listings.json")
