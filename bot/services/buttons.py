"""E'lonlar ostidagi tugmalarni matndan parse qilish.

Format (har bir qator — klaviaturaning bitta qatori, bir qatordagi tugmalar " | " bilan ajratiladi):

    Matn - https://havola.uz            -> havola (URL) tugmasi
    Matn - webapp:https://site.uz       -> Web App tugmasi
    Matn - share:Ulashiladigan matn     -> "Ulashish" tugmasi (matn + bot havolasi)
    Matn - alert:Ko'rsatiladigan matn   -> bosilganda oyna (alert) chiqaradi
    Matn - ref                          -> foydalanuvchining shaxsiy taklif havolasini ulashish
    Matn - bot                          -> botga havola
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot.db import Database


class ButtonParseError(ValueError):
    pass


@dataclass
class ButtonSpec:
    text: str
    kind: str  # url | webapp | share | alert | ref | bot
    value: str = ""


def ref_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start={user_id}"


def share_url(url: str, text: str = "") -> str:
    result = f"https://t.me/share/url?url={quote(url, safe='')}"
    if text:
        result += f"&text={quote(text, safe='')}"
    return result


async def parse_buttons(raw: str, db: Database) -> list[list[ButtonSpec]]:
    rows: list[list[ButtonSpec]] = []
    for line_no, line in enumerate(raw.strip().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        row: list[ButtonSpec] = []
        for part in line.split("|"):
            part = part.strip()
            if " - " not in part:
                raise ButtonParseError(f"{line_no}-qator: «{part}» — «Matn - qiymat» formatida yozing.")
            text, value = (x.strip() for x in part.split(" - ", 1))
            if not text or not value:
                raise ButtonParseError(f"{line_no}-qator: tugma matni yoki qiymati bo'sh.")
            lowered = value.lower()
            if lowered in ("ref", "bot"):
                row.append(ButtonSpec(text, lowered))
            elif lowered.startswith("alert:"):
                alert_text = value[6:].strip()
                if not alert_text or len(alert_text) > 200:
                    raise ButtonParseError(f"{line_no}-qator: alert matni 1–200 belgi bo'lishi kerak.")
                alert_id = await db.add_alert(alert_text)
                row.append(ButtonSpec(text, "alert", str(alert_id)))
            elif lowered.startswith("share:"):
                row.append(ButtonSpec(text, "share", value[6:].strip()))
            elif lowered.startswith("webapp:"):
                url = value[7:].strip()
                if not url.startswith("https://"):
                    raise ButtonParseError(f"{line_no}-qator: Web App havolasi https:// bilan boshlanishi kerak.")
                row.append(ButtonSpec(text, "webapp", url))
            elif lowered.startswith(("http://", "https://", "tg://")):
                row.append(ButtonSpec(text, "url", value))
            elif value.startswith("@"):
                row.append(ButtonSpec(text, "url", f"https://t.me/{value[1:]}"))
            else:
                raise ButtonParseError(f"{line_no}-qator: «{value}» — noma'lum tugma turi.")
        if row:
            rows.append(row)
    if not rows:
        raise ButtonParseError("Birorta ham tugma topilmadi.")
    return rows


def needs_personal_markup(rows: list[list[ButtonSpec]]) -> bool:
    return any(b.kind == "ref" for row in rows for b in row)


def build_markup(
    rows: list[list[ButtonSpec]] | None, bot_username: str, user_id: int | None = None
) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    keyboard: list[list[InlineKeyboardButton]] = []
    bot_link = f"https://t.me/{bot_username}"
    for row in rows:
        kb_row = []
        for spec in row:
            if spec.kind == "url":
                kb_row.append(InlineKeyboardButton(text=spec.text, url=spec.value))
            elif spec.kind == "webapp":
                kb_row.append(InlineKeyboardButton(text=spec.text, web_app=WebAppInfo(url=spec.value)))
            elif spec.kind == "alert":
                kb_row.append(InlineKeyboardButton(text=spec.text, callback_data=f"alert:{spec.value}"))
            elif spec.kind == "share":
                kb_row.append(InlineKeyboardButton(text=spec.text, url=share_url(bot_link, spec.value)))
            elif spec.kind == "bot":
                kb_row.append(InlineKeyboardButton(text=spec.text, url=bot_link))
            elif spec.kind == "ref":
                link = ref_link(bot_username, user_id) if user_id else bot_link
                kb_row.append(InlineKeyboardButton(text=spec.text, url=share_url(link)))
        keyboard.append(kb_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
