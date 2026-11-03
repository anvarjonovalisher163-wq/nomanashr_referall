"""Klaviaturalar."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from bot import texts
from bot.db import Channel, Database

ADMIN_BUTTON = "⚙️ Admin panel"


def ikb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """[(matn, callback_data), ...] qatorlaridan inline klaviatura yasaydi."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def main_menu(db: Database, is_admin: bool = False) -> ReplyKeyboardMarkup:
    label = lambda key: KeyboardButton(text=texts.get(db, key))  # noqa: E731
    rows = [
        [label("btn_ref"), label("btn_stats")],
        [label("btn_top"), label("btn_about")],
        [label("btn_winners")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=ADMIN_BUTTON)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def subscribe_kb(db: Database, channels: list[Channel]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=texts.render(db, "btn_channel", title=ch.title), url=ch.invite_link)]
        for ch in channels
    ]
    rows.append([InlineKeyboardButton(text=texts.get(db, "btn_check_sub"), callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_main_kb() -> InlineKeyboardMarkup:
    return ikb(
        [
            [("📊 Statistika", "adm:stats"), ("📢 E'lon yuborish", "adm:broadcast")],
            [("🎯 Konkurs", "adm:contest"), ("📡 Majburiy kanallar", "adm:channels")],
            [("📝 Bot matnlari", "adm:texts"), ("⚙️ Bot sozlamalari", "adm:settings")],
            [("👮 Adminlar", "adm:admins"), ("❌ Yopish", "adm:close")],
        ]
    )


def back_kb(target: str = "adm:main") -> InlineKeyboardMarkup:
    return ikb([[("⬅️ Orqaga", target)]])


def cancel_kb() -> InlineKeyboardMarkup:
    return ikb([[("❌ Bekor qilish", "adm:cancel")]])
