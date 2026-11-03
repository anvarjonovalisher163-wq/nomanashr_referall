"""Oddiy foydalanuvchi uchun handlerlar."""
from __future__ import annotations

import html
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, Filter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import texts
from bot.config import Config
from bot.db import Database
from bot.keyboards import main_menu, subscribe_kb
from bot.services import subscription
from bot.services.buttons import ref_link, share_url
from bot.services.contest import draw_at_text, on_user_verified, winners_text

router = Router(name="user")


class MenuButton(Filter):
    """Menyu tugmasini admin o'zgartirgan joriy yozuvi (yoki standart yozuvi) bo'yicha taniydi."""

    def __init__(self, key: str) -> None:
        self.key = key

    async def __call__(self, message: Message, db: Database, **_: Any) -> bool:
        return message.text is not None and message.text in (
            texts.get(db, self.key),
            texts.TEXTS[self.key].default,
        )


async def send_welcome(message: Message, db: Database, is_admin: bool, name: str) -> None:
    text = texts.render(db, "welcome_text", name=html.escape(name))
    await message.answer(text, reply_markup=main_menu(db, is_admin))


def contest_state(db: Database) -> str:
    if db.get_bool("contest_drawn"):
        return texts.get(db, "state_drawn")
    if db.get_bool("contest_active"):
        return texts.get(db, "state_active")
    return texts.get(db, "state_inactive")


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, is_admin: bool) -> None:
    await send_welcome(message, db, is_admin, message.from_user.full_name)


@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, bot: Bot, db: Database, is_admin: bool) -> None:
    subscription.invalidate(call.from_user.id)
    missing = await subscription.unsubscribed_channels(bot, db, call.from_user.id, use_cache=False)
    if missing:
        await call.answer(texts.get(db, "sub_alert_not_subscribed"), show_alert=True)
        try:
            await call.message.edit_reply_markup(reply_markup=subscribe_kb(db, missing))
        except Exception:  # noqa: BLE001 — klaviatura o'zgarmagan bo'lishi mumkin
            pass
        return
    await call.answer(texts.get(db, "sub_alert_confirmed"))
    try:
        await call.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await on_user_verified(bot, db, call.from_user.id)
    await send_welcome(call.message, db, is_admin, call.from_user.full_name)


@router.callback_query(F.data.startswith("alert:"))
async def alert_button(call: CallbackQuery, db: Database) -> None:
    alert_id = call.data.split(":", 1)[1]
    text = await db.get_alert(int(alert_id)) if alert_id.isdigit() else None
    await call.answer(text or "—", show_alert=True)


@router.message(MenuButton("btn_ref"))
async def my_link(message: Message, db: Database, bot_username: str) -> None:
    link = ref_link(bot_username, message.from_user.id)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=texts.get(db, "btn_share"),
                url=share_url(link, texts.get(db, "share_text")),
            )
        ]]
    )
    await message.answer(
        texts.render(db, "ref_link_text", link=link, required=db.get_int("required_refs")),
        reply_markup=kb,
    )


@router.message(MenuButton("btn_about"))
async def about(message: Message, db: Database, config: Config) -> None:
    await message.answer(
        texts.render(
            db,
            "about_text",
            status=contest_state(db),
            required=db.get_int("required_refs"),
            winners=db.get_int("winners_count"),
            date=draw_at_text(db, config),
            prize=texts.get(db, "prize_text"),
        )
    )


@router.message(MenuButton("btn_winners"))
async def winners(message: Message, db: Database, is_admin: bool) -> None:
    if not db.get_bool("contest_drawn"):
        # Eski klaviaturada qolgan tugma bosilsa — menyuni yangilab yuboramiz
        await message.answer(texts.get(db, "winners_not_yet"), reply_markup=main_menu(db, is_admin))
        return
    await message.answer(await winners_text(db, db.contest_id))


@router.message()
async def fallback(message: Message, db: Database, is_admin: bool) -> None:
    """Noma'lum xabar: menyuni (yangilangan tugma yozuvlari bilan) qayta yuboradi."""
    await message.answer(texts.get(db, "menu_hint"), reply_markup=main_menu(db, is_admin))
