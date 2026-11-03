"""Majburiy obuna kanallarini boshqarish."""
from __future__ import annotations

import html

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db import Database
from bot.handlers.admin.common import AdminStates, IsAdmin, show
from bot.keyboards import cancel_kb, ikb

router = Router(name="admin_channels")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _render(call: CallbackQuery, db: Database) -> None:
    channels = await db.channels()
    if channels:
        lines = [
            f"{i}. <b>{html.escape(ch.title)}</b> — <code>{ch.chat_id}</code>\n   {html.escape(ch.invite_link)}"
            for i, ch in enumerate(channels, start=1)
        ]
        body = "\n".join(lines)
    else:
        body = "Hozircha majburiy kanal yo'q."
    rows = [[(f"🗑 {ch.title[:30]}", f"ch:del:{ch.id}")] for ch in channels]
    rows.append([("➕ Kanal qo'shish", "ch:add")])
    rows.append([("⬅️ Orqaga", "adm:main")])
    await show(call, f"📡 <b>Majburiy kanallar</b>\n\n{body}", ikb(rows))


@router.callback_query(F.data == "adm:channels")
async def channels_menu(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await _render(call, db)


@router.callback_query(F.data.startswith("ch:del:"))
async def delete_channel(call: CallbackQuery, db: Database) -> None:
    await db.remove_channel(int(call.data.split(":")[2]))
    await _render(call, db)


@router.callback_query(F.data == "ch:add")
async def add_channel(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.channel_add)
    await show(
        call,
        "➕ <b>Kanal qo'shish</b>\n\n"
        "1. Botni kanal/guruhga <b>admin</b> qilib qo'shing.\n"
        "2. Kanal <code>@username</code> ini yoki ID sini (<code>-100...</code>) yuboring, "
        "yoki kanaldan istalgan postni shu yerga <b>forward</b> qiling.\n\n"
        "Yopiq kanal uchun ID dan keyin probel bilan taklif havolasini ham yozishingiz mumkin:\n"
        "<code>-1001234567890 https://t.me/+AbCdEf</code>",
        cancel_kb(),
    )


@router.message(AdminStates.channel_add)
async def got_channel(message: Message, state: FSMContext, bot: Bot, db: Database) -> None:
    custom_link: str | None = None
    origin_chat = getattr(message.forward_origin, "chat", None) if message.forward_origin else None
    if origin_chat:
        chat_ref: int | str = origin_chat.id
    elif message.text:
        parts = message.text.split()
        raw = parts[0].strip()
        if len(parts) > 1 and parts[1].startswith("https://"):
            custom_link = parts[1]
        if raw.startswith("https://t.me/") and "+" not in raw:
            raw = "@" + raw.removeprefix("https://t.me/").strip("/")
        chat_ref = int(raw) if raw.lstrip("-").isdigit() else raw
    else:
        await message.answer("⚠️ Kanal username, ID yoki forward qilingan post yuboring.", reply_markup=cancel_kb())
        return

    try:
        chat = await bot.get_chat(chat_ref)
        me = await bot.get_chat_member(chat.id, bot.id)
    except TelegramAPIError as exc:
        await message.answer(
            f"⚠️ Kanal topilmadi yoki bot unga qo'shilmagan.\n<code>{html.escape(str(exc))}</code>",
            reply_markup=cancel_kb(),
        )
        return
    if me.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
        await message.answer("⚠️ Bot bu kanalda admin emas. Avval botni admin qiling.", reply_markup=cancel_kb())
        return

    link = custom_link or (f"https://t.me/{chat.username}" if chat.username else chat.invite_link)
    if not link:
        try:
            link = await bot.export_chat_invite_link(chat.id)
        except TelegramAPIError:
            await message.answer(
                "⚠️ Taklif havolasini olib bo'lmadi. ID va havolani birga yuboring:\n"
                "<code>-1001234567890 https://t.me/+AbCdEf</code>",
                reply_markup=cancel_kb(),
            )
            return

    await db.add_channel(chat.id, chat.title or str(chat.id), link)
    await state.clear()
    await message.answer(
        f"✅ <b>{html.escape(chat.title or '')}</b> majburiy kanallarga qo'shildi.",
        reply_markup=ikb([[("📡 Kanallar", "adm:channels"), ("🏠 Panel", "adm:main")]]),
    )
