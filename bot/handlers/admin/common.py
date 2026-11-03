"""Admin bo'limlari uchun umumiy narsalar."""
from __future__ import annotations

from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Filter
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup


class IsAdmin(Filter):
    async def __call__(self, event: Any, is_admin: bool = False) -> bool:
        return is_admin


class AdminStates(StatesGroup):
    broadcast_message = State()
    broadcast_buttons = State()
    broadcast_confirm = State()
    channel_add = State()
    admin_add = State()
    set_required = State()
    set_winners = State()
    set_date = State()
    set_prize = State()
    set_welcome = State()


async def show(call: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    """Joriy xabarni tahrirlaydi, iloji bo'lmasa yangisini yuboradi."""
    try:
        await call.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            await call.message.answer(text, reply_markup=kb, disable_web_page_preview=True)
    try:
        await call.answer()
    except TelegramBadRequest:
        pass  # callback allaqachon javob olgan bo'lishi mumkin
