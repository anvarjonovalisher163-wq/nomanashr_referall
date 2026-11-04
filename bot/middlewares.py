"""Foydalanuvchini ro'yxatga olish, bot holati va majburiy obunani tekshirish."""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import Config
from bot import texts
from bot.db import Database
from bot.keyboards import subscribe_kb
from bot.services import notifier, subscription
from bot.services.contest import on_user_verified
from bot.services.rich import send_rich

_TOUCH_EVERY = 3600  # soniya
_last_touch: dict[int, float] = {}

# Obuna tekshiruvisiz ishlaydigan callbacklar
_FREE_CALLBACKS = ("check_sub", "alert:")


def _parse_referrer(text: str | None, user_id: int) -> int | None:
    if not text or not text.startswith("/start"):
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip().removeprefix("ref")
    if not payload.isdigit():
        return None
    referrer = int(payload)
    return referrer if referrer != user_id else None


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery):
            chat = event.message.chat if event.message else None
        else:
            return await handler(event, data)

        user = event.from_user
        # Bot faqat shaxsiy chatda ishlaydi
        if user is None or user.is_bot or chat is None or chat.type != ChatType.PRIVATE:
            return None

        db: Database = data["db"]
        config: Config = data["config"]
        bot: Bot = data["bot"]

        # 1) Ro'yxatga olish
        existing = await db.get_user(user.id)
        if existing is None:
            referrer_id = None
            if isinstance(event, Message):
                referrer_id = _parse_referrer(event.text, user.id)
                if referrer_id and not await db.get_user(referrer_id):
                    referrer_id = None
            if await db.add_user(user.id, user.full_name, user.username, referrer_id):
                await notifier.push(db, config, user.id, user.full_name, user.username, referrer_id)
        else:
            if existing.full_name != user.full_name or existing.username != user.username or existing.is_blocked:
                await db.update_user(user.id, user.full_name, user.username)
            # Oxirgi faollik — bazaga ko'pi bilan soatiga bir marta yoziladi
            now = time.monotonic()
            if now - _last_touch.get(user.id, -_TOUCH_EVERY) >= _TOUCH_EVERY:
                _last_touch[user.id] = now
                await db.touch(user.id)

        is_admin = user.id in config.admin_ids or user.id in db.db_admins
        data["is_admin"] = is_admin
        # Sozlama o'chiq bo'lsa, do'st havola orqali botga kirishi bilanoq taklif sanaladi
        if is_admin or not db.get_bool("ref_requires_sub"):
            await on_user_verified(bot, db, user.id)
        if is_admin:
            return await handler(event, data)

        # 2) Bot holati
        if not db.get_bool("bot_enabled"):
            text = texts.get(db, "bot_disabled")
            if isinstance(event, CallbackQuery):
                await event.answer(texts.strip_html(text)[:200], show_alert=True)
            else:
                await send_rich(bot, user.id, db, "bot_disabled")
            return None

        if isinstance(event, CallbackQuery) and (event.data or "").startswith(_FREE_CALLBACKS):
            return await handler(event, data)

        # 3) Majburiy obuna
        missing = await subscription.unsubscribed_channels(bot, db, user.id)
        await db.track_subscriptions(user.id, {ch.chat_id for ch in missing})
        if missing:
            if isinstance(event, CallbackQuery):
                await event.answer(texts.get(db, "sub_alert_required"), show_alert=True)
            await send_rich(bot, user.id, db, "sub_prompt", reply_markup=subscribe_kb(db, missing))
            return None

        await on_user_verified(bot, db, user.id)
        return await handler(event, data)
