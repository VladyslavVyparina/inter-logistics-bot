from __future__ import annotations

from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import GOOGLE_SHEET_ID, GOOGLE_SHEET_RANGE


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_service():
    credentials = service_account.Credentials.from_service_account_file(
        "service_account.json", scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=credentials)
    return service.spreadsheets()


def append_row(
    date_str: str,
    name: str,
    username: Optional[str],
    phone: str,
    answers: str,
    tag: str,
    contact_method: Optional[str],
) -> None:
    try:
        sheet = _get_service()

        values = [
            [
                date_str,
                name,
                username or "",
                phone,
                answers,
                tag,
                contact_method or "",
            ]
        ]

        body = {"values": values}
        sheet.values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=GOOGLE_SHEET_RANGE,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()
    except FileNotFoundError:
        print("Google Sheets: файл service_account.json не знайдено.")
    except HttpError as e:
        print(f"Google Sheets API error: {e}")
