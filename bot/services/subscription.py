"""Majburiy kanallarga obunani tekshirish (qisqa muddatli kesh bilan)."""
from __future__ import annotations

import logging
import time

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError

from bot.db import Channel, Database

log = logging.getLogger(__name__)

_NOT_MEMBER = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
_CACHE_TTL = 60  # soniya
_cache: dict[tuple[int, int], float] = {}  # (user_id, chat_id) -> obuna tasdiqlangan vaqt


def invalidate(user_id: int) -> None:
    for key in [k for k in _cache if k[0] == user_id]:
        _cache.pop(key, None)


async def is_member(bot: Bot, chat_id: int, user_id: int, use_cache: bool = True) -> bool:
    key = (user_id, chat_id)
    if use_cache and time.monotonic() - _cache.get(key, 0) < _CACHE_TTL:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError as exc:
        # Bot kanalda admin emas yoki kanal o'chirilgan — foydalanuvchini bloklamaymiz.
        log.warning("Obunani tekshirib bo'lmadi (chat %s): %s", chat_id, exc)
        return True
    if member.status in _NOT_MEMBER:
        return False
    # "restricted" holatida is_member=False bo'lishi mumkin
    if member.status == ChatMemberStatus.RESTRICTED and not getattr(member, "is_member", True):
        return False
    now = time.monotonic()
    if len(_cache) > 20_000:
        # Eskirgan yozuvlarni tozalash — kesh cheksiz o'smasin
        for k in [k for k, t in _cache.items() if now - t >= _CACHE_TTL]:
            _cache.pop(k, None)
    _cache[key] = now
    return True


async def unsubscribed_channels(
    bot: Bot, db: Database, user_id: int, use_cache: bool = True
) -> list[Channel]:
    result = []
    for channel in await db.channels():
        if not await is_member(bot, channel.chat_id, user_id, use_cache):
            result.append(channel)
    return result
