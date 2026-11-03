"""Klaviaturalar."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot.db import Channel


class Btn:
    """Asosiy menyu tugmalari matni."""

    REF = "🔗 Taklif havolam"
    STATS = "📊 Mening natijam"
    TOP = "🏆 Reyting"
    ABOUT = "ℹ️ Konkurs haqida"
    WINNERS = "🎁 G'oliblar"
    ADMIN = "⚙️ Admin panel"


def ikb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """[(matn, callback_data), ...] qatorlaridan inline klaviatura yasaydi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=Btn.REF), KeyboardButton(text=Btn.STATS)],
        [KeyboardButton(text=Btn.TOP), KeyboardButton(text=Btn.ABOUT)],
        [KeyboardButton(text=Btn.WINNERS)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=Btn.ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def subscribe_kb(channels: list[Channel]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"➕ {ch.title}", url=ch.invite_link)] for ch in channels]
    rows.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_main_kb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("📊 Statistika", "adm:stats"), ("📢 E'lon yuborish", "adm:broadcast")],
            [("🎯 Konkurs", "adm:contest"), ("📡 Majburiy kanallar", "adm:channels")],
            [("⚙️ Bot sozlamalari", "adm:settings"), ("👮 Adminlar", "adm:admins")],
            [("❌ Yopish", "adm:close")],
        ]
    )


def back_kb(target: str = "adm:main") -> InlineKeyboardMarkup:
    return ikb([[("⬅️ Orqaga", target)]])


def cancel_kb() -> InlineKeyboardMarkup:
    return ikb([[("❌ Bekor qilish", "adm:cancel")]])
