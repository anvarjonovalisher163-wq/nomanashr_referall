"""Bot matnlarini media (rasm, video, ...) va tugmalar bilan yuborish.

Admin "📝 Bot matnlari" bo'limida xabarga media va tugmalar biriktirishi mumkin. Ular `settings`
jadvalida saqlanadi:
    <key>__media    -> "photo:<file_id>" (photo | video | animation | document | audio)
    <key>__buttons  -> tugmalar JSON ko'rinishida (services/buttons.py formati)
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

from bot import texts
from bot.db import Database
from bot.services.buttons import ButtonSpec, build_markup

log = logging.getLogger(__name__)

CAPTION_LIMIT = 1024
MEDIA_KINDS = ("photo", "video", "animation", "document", "audio")
MEDIA_NAMES = {
    "photo": "rasm",
    "video": "video",
    "animation": "GIF",
    "document": "fayl",
    "audio": "audio",
}

# Botning @username i (ref/bot/share tugmalari uchun) — ishga tushganda o'rnatiladi.
BOT_USERNAME = ""


def media_key(key: str) -> str:
    return f"{key}__media"


def buttons_key(key: str) -> str:
    return f"{key}__buttons"


def get_media(db: Database, key: str) -> tuple[str, str] | None:
    raw = db.get(media_key(key))
    if not raw or ":" not in raw:
        return None
    kind, file_id = raw.split(":", 1)
    return (kind, file_id) if kind in MEDIA_KINDS else None


def get_buttons(db: Database, key: str) -> list[list[ButtonSpec]] | None:
    raw = db.get(buttons_key(key))
    if not raw:
        return None
    try:
        return [[ButtonSpec(**b) for b in row] for row in json.loads(raw)]
    except (ValueError, TypeError):
        return None


def dump_buttons(rows: list[list[ButtonSpec]]) -> str:
    return json.dumps([[asdict(b) for b in row] for row in rows], ensure_ascii=False)


def extract_media(message: Message) -> tuple[str, str] | None:
    """Xabardagi mediani (tur, file_id) ko'rinishida qaytaradi."""
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.animation:  # GIF da document ham bo'ladi — avval animation
        return "animation", message.animation.file_id
    if message.video:
        return "video", message.video.file_id
    if message.audio:
        return "audio", message.audio.file_id
    if message.document:
        return "document", message.document.file_id
    return None


def _merge(base, extra: InlineKeyboardMarkup | None):
    """Mavjud klaviaturaga admin qo'shgan tugmalarni qo'shadi.

    Qaytaradi: (asosiy xabar klaviaturasi, alohida yuboriladigan reply-klaviatura yoki None)
    """
    if extra is None:
        return base, None
    if base is None:
        return extra, None
    if isinstance(base, InlineKeyboardMarkup):
        return InlineKeyboardMarkup(inline_keyboard=base.inline_keyboard + extra.inline_keyboard), None
    # Bitta xabarda ham reply, ham inline klaviatura bo'lolmaydi
    return extra, base


async def _send_media(bot: Bot, chat_id: int, kind: str, file_id: str, caption: str | None, markup) -> None:
    method = {
        "photo": bot.send_photo,
        "video": bot.send_video,
        "animation": bot.send_animation,
        "document": bot.send_document,
        "audio": bot.send_audio,
    }[kind]
    await method(chat_id, file_id, caption=caption, reply_markup=markup)


async def send_rich(
    bot: Bot,
    chat_id: int,
    db: Database,
    key: str,
    text: str | None = None,
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
    **values: object,
) -> None:
    """`key` matnini (media va tugmalari bilan) yuboradi.

    `text` berilsa — tayyor matn ishlatiladi (masalan, g'oliblar ro'yxati), aks holda
    `texts.render(db, key, **values)`.
    """
    if text is None:
        text = texts.render(db, key, **values)
    media = get_media(db, key)
    rows = get_buttons(db, key)
    extra = build_markup(rows, BOT_USERNAME, chat_id) if rows else None
    markup, separate_reply = _merge(reply_markup, extra)

    if media:
        kind, file_id = media
        try:
            if len(text) <= CAPTION_LIMIT:
                await _send_media(bot, chat_id, kind, file_id, text, markup)
            else:
                # Izoh juda uzun — avval media, keyin matn
                await _send_media(bot, chat_id, kind, file_id, None, None)
                await bot.send_message(chat_id, text, reply_markup=markup)
        except TelegramBadRequest as exc:
            # Fayl topilmasa (masalan, bot tokeni almashgan) — faqat matn yuboriladi
            log.warning("Media yuborilmadi (%s): %s", key, exc)
            await bot.send_message(chat_id, text, reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, reply_markup=markup)

    if separate_reply is not None:
        await bot.send_message(chat_id, texts.get(db, "menu_hint"), reply_markup=separate_reply)
