from __future__ import annotations

import re

PHONE_RE = re.compile(
    r"(?:(?:\+|00)\d{1,3}[\s\-()]*)?(?:\(?\d{2,4}\)?[\s\-()]*)?\d{3}[\s\-()]*\d{2,3}[\s\-()]*\d{2,3}"
)
LONG_DIGIT_RE = re.compile(r"\b\d{10,15}\b")
USERNAME_RE = re.compile(r"@[\w]{3,32}")
URL_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me|telegram\.dog|wa\.me|api\.whatsapp\.com|"
    r"whatsapp\.com|viber\.com|bit\.ly|tinyurl\.com)/[^\s]+",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
CONTACT_LABEL_RE = re.compile(
    r"(?i)(?:тел(?:ефон)?|phone|viber|whats?app|telegram|tg|вайбер|ватсап)\s*[:\-–]?\s*$",
    re.MULTILINE,
)
ROUTE_RE = re.compile(
    r"[A-Za-zА-Яа-яІіЇїЄєҐґ]{3,}\s*[-–—/]\s*[A-Za-zА-Яа-яІіЇїЄєҐґ]{3,}"
)

TRANSPORT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"вільн\w*.{0,20}(транспорт|авто|машин)",
        r"свободн\w*.{0,20}(транспорт|авто|машин|тент|реф)",
        r"ищу\s+груз",
        r"шукаю\s+(вантаж|груз|загрузк)",
        r"ищу\s+загрузк",
        r"порожн",
        r"дислокац",
        r"есть\s+(свободн|авто|машин)",
        r"є\s+(вільн|авто|машин)",
        r"готов[аыий]*.{0,12}(машин|авто|їхат|ехат|заїхат|заехат)",
        r"простой",
        r"empty\s+(truck|trailer)",
        r"free\s+(truck|vehicle|trailer)",
        r"збір.{0,10}(авто|машин)",
        r"сбор.{0,10}(авто|машин)",
    ]
]

CARGO_ONLY_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"є\s+вантаж",
        r"есть\s+груз",
        r"имеется\s+груз",
        r"вантаж\s+є",
        r"груз\s+есть",
        r"шукаю\s+(машин|авто|транспорт)",
        r"ищу\s+(машин|авто|транспорт|машину)",
        r"нуж(ен|на)\s+(машин|авто|транспорт)",
        r"потріб(ен|на)\s+(машин|авто|транспорт)",
        r"шукаємо\s+транспорт",
        r"нужен\s+транспорт",
    ]
]

VEHICLE_HINTS = [
    "тент",
    "реф",
    "рефриж",
    "контейнер",
    "автовоз",
    "цистерн",
    "мега",
    "площадк",
    "низкорамн",
    "13.6",
    "90м",
    "92м",
    "120м",
]


def extract_phones(text: str) -> str:
    if not text:
        return ""
    found = PHONE_RE.findall(text) + LONG_DIGIT_RE.findall(text)
    cleaned = []
    seen = set()
    for item in found:
        compact = re.sub(r"\s+", " ", item).strip()
        digits = re.sub(r"\D", "", compact)
        if len(digits) < 10 or digits in seen:
            continue
        seen.add(digits)
        cleaned.append(compact)
    return ", ".join(cleaned)


def strip_contacts(text: str) -> str:
    if not text:
        return ""
    cleaned = URL_RE.sub("", text)
    cleaned = EMAIL_RE.sub("", cleaned)
    cleaned = USERNAME_RE.sub("", cleaned)
    cleaned = PHONE_RE.sub("", cleaned)
    cleaned = LONG_DIGIT_RE.sub("", cleaned)
    cleaned = CONTACT_LABEL_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip(" \n\t,;:-")


def is_free_transport(text: str) -> bool:
    if not text or len(text.strip()) < 12:
        return False
    lowered = text.lower()
    if any(p.search(text) for p in CARGO_ONLY_PATTERNS) and not any(
        p.search(text) for p in TRANSPORT_PATTERNS
    ):
        return False
    if any(p.search(text) for p in TRANSPORT_PATTERNS):
        return True
    has_route = bool(ROUTE_RE.search(text))
    has_vehicle = any(hint in lowered for hint in VEHICLE_HINTS)
    return has_route and has_vehicle


def looks_like_our_repost(text: str) -> bool:
    if not text:
        return False
    if "ВІЛЬНИЙ ТРАНСПОРТ" not in text:
        return False
    return "Залишити заявку" in text or "Місце дислокації" in text
