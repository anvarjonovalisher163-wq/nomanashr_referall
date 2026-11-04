"""Yangi foydalanuvchilar haqida adminlarga yoki log kanalga xabar berish.

Telegram bitta chatga daqiqasiga ~20 tadan ko'p xabar yuborishga ruxsat bermaydi, shuning uchun
yangi foydalanuvchilar navbatga yig'iladi va har 10 soniyada bitta umumiy xabar bo'lib yuboriladi.
"""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from bot.config import Config
from bot.db import Database

log = logging.getLogger(__name__)

INTERVAL = 10  # soniya
MAX_PER_MESSAGE = 25

_queue: list[str] = []


def _mention(user_id: int, name: str | None, username: str | None) -> str:
    text = f'<a href="tg://user?id={user_id}">{html.escape(name or str(user_id))}</a>'
    if username:
        text += f" @{html.escape(username)}"
    return text


async def push(
    db: Database, config: Config, user_id: int, full_name: str, username: str | None, referrer_id: int | None
) -> None:
    """Yangi foydalanuvchini navbatga qo'shadi (sozlama yoqilgan bo'lsa)."""
    if not db.get_bool("notify_new_users"):
        return
    line = f"👤 {_mention(user_id, full_name, username)} — <code>{user_id}</code>"
    if referrer_id:
        ref = await db.get_user(referrer_id)
        line += f"\n      ↳ taklif qildi: {_mention(referrer_id, ref.full_name if ref else None, ref.username if ref else None)}"
    line += f"\n      🕒 {datetime.now(config.tz):%d.%m.%Y %H:%M}"
    _queue.append(line)


def _targets(db: Database, config: Config) -> list[int]:
    raw = db.get("log_chat_id")
    if raw and raw.lstrip("-").isdigit():
        return [int(raw)]
    return sorted(config.admin_ids)


async def notifier_loop(bot: Bot, db: Database, config: Config) -> None:
    while True:
        await asyncio.sleep(INTERVAL)
        if not _queue:
            continue
        batch = _queue[:MAX_PER_MESSAGE]
        del _queue[:MAX_PER_MESSAGE]
        total = (await db.stats())["users"]
        text = f"🆕 <b>Yangi foydalanuvchilar: {len(batch)}</b> (jami: {total})\n\n" + "\n".join(batch)
        for chat_id in _targets(db, config):
            try:
                await bot.send_message(chat_id, text, disable_web_page_preview=True)
            except TelegramRetryAfter as exc:
                _queue[:0] = batch  # keyinroq qayta yuboriladi
                await asyncio.sleep(exc.retry_after)
                break
            except TelegramAPIError as exc:
                log.warning("Yangi foydalanuvchi xabari yuborilmadi (%s): %s", chat_id, exc)
