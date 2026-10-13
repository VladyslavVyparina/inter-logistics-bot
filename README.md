# Inter Logistics bot

A Telegram bot that interviews a shipper step by step and posts a finished freight request into an operations chat, with a copy written to Google Sheets.

## Problem

Freight requests arrived as unstructured messages: sometimes a city, sometimes a weight, rarely a truck type. Dispatchers were rewriting them into a sheet and into the working chat.

## What was built

A guided funnel. The bot asks, in order:

- Cargo
- Country of origin
- Country of destination
- Truck type: tilt, refrigerator, container, open, car carrier, tank, or other
- Volume
- Weight
- Number of trucks
- Freight rate
- Phone number

When the last answer is in, the request is sent to the configured Telegram chat. `google_sheets.py` writes the same row to a sheet. `listings.py` and `locations.py` hold the catalogs the questions use. `scheduler.py` is the timed side of the same bot.

## How it works

Each answer is stored on the user until the funnel is complete. The truck type is a button, not free text, so the sheet stays consistent. The Google client uses a service account. That JSON key is not in this repository. Put your own key next to the bot and point `config.py` at it locally.

## Stack

Python, aiogram, Google Sheets.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
python bot.py
```

## What this public copy leaves out

`service_account.json`.
