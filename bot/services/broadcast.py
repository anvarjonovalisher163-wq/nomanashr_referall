"""Barcha foydalanuvchilarga e'lon yuborish (Telegram limitlariga rioya qilgan holda)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramAPIError

from bot.db import Database
from bot.services.buttons import ButtonSpec, build_markup, needs_personal_markup
from bot.services.rich import send_rich

log = logging.getLogger(__name__)

SEND_DELAY = 1 / 25  # ~25 xabar/soniya


@dataclass
class BroadcastResult:
    total: int = 0
    sent: int = 0
    failed: int = 0
    blocked: int = 0
    skipped: int = 0


async def _send_one(bot: Bot, send, user_id: int, db: Database, result: BroadcastResult) -> None:
    for _ in range(3):
        try:
            await send(user_id)
            result.sent += 1
            return
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramForbiddenError:
            await db.set_blocked(user_id)
            result.blocked += 1
            return
        except TelegramAPIError as exc:
            log.info("Xabar yuborilmadi %s: %s", user_id, exc)
            result.failed += 1
            return
    result.failed += 1


async def broadcast_copy(
    bot: Bot,
    db: Database,
    from_chat_id: int,
    message_id: int,
    buttons: list[list[ButtonSpec]] | None,
    bot_username: str,
    progress=None,
    user_ids: list[int] | None = None,
    should_send=None,
) -> BroadcastResult:
    """Admin yuborgan xabarni (har qanday turdagi) foydalanuvchilarga nusxalaydi.

    `user_ids` berilmasa — hammaga. `should_send(uid)` False qaytarsa, o'sha foydalanuvchi o'tkazib yuboriladi.
    """
    if user_ids is None:
        user_ids = await db.all_user_ids()
    result = BroadcastResult(total=len(user_ids))
    personal = needs_personal_markup(buttons or [])
    common_markup = None if personal else build_markup(buttons, bot_username)

    async def send(uid: int):
        markup = build_markup(buttons, bot_username, uid) if personal else common_markup
        await bot.copy_message(uid, from_chat_id, message_id, reply_markup=markup)

    for index, uid in enumerate(user_ids, start=1):
        if should_send is not None and not await should_send(uid):
            result.skipped += 1
        else:
            await _send_one(bot, send, uid, db, result)
            await asyncio.sleep(SEND_DELAY)
        if progress and index % 200 == 0:
            await progress(result, index)
    return result


async def broadcast_text(
    bot: Bot, db: Database, key: str, text: str, exclude: set[int] | None = None, reply_markup=None
) -> BroadcastResult:
    """`key` matnining media va tugmalari bilan birga tayyor `text` ni hammaga yuboradi."""
    user_ids = [u for u in await db.all_user_ids() if u not in (exclude or set())]
    result = BroadcastResult(total=len(user_ids))

    async def send(uid: int):
        await send_rich(bot, uid, db, key, text=text, reply_markup=reply_markup)

    for uid in user_ids:
        await _send_one(bot, send, uid, db, result)
        await asyncio.sleep(SEND_DELAY)
    return result
