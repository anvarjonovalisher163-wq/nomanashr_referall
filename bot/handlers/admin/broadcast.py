"""E'lon yuborish: istalgan turdagi xabar + uning ostiga har xil tugmalar."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db import Database
from bot.handlers.admin.common import AdminStates, IsAdmin, show
from bot.keyboards import cancel_kb, ikb
from bot.services.broadcast import BroadcastResult, broadcast_copy
from bot.services.buttons import ButtonParseError, ButtonSpec, build_markup, parse_buttons

log = logging.getLogger(__name__)

router = Router(name="admin_broadcast")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

BUTTONS_HELP = (
    "🔘 <b>Tugmalarni yuboring.</b>\n\n"
    "Har bir qator — alohida qator. Bitta qatorga bir nechta tugma qo'yish uchun <code>|</code> bilan ajrating.\n\n"
    "<b>Tugma turlari:</b>\n"
    "• <code>Kanalimiz - https://t.me/kanal</code> — havola\n"
    "• <code>Kanal - @kanal_username</code> — Telegram havola\n"
    "• <code>Ilova - webapp:https://site.uz</code> — Web App\n"
    "• <code>Ulashish - share:Zo'r bot ekan!</code> — botni ulashish\n"
    "• <code>Taklif qilish - ref</code> — har bir foydalanuvchining <b>shaxsiy taklif havolasini</b> ulashish\n"
    "• <code>Botga o'tish - bot</code> — botga havola\n"
    "• <code>Shartlar - alert:3 ta do'st taklif qiling</code> — bosilganda oyna chiqaradi\n\n"
    "<b>Misol:</b>\n"
    "<code>Kanal - @kanal | Sayt - https://site.uz\n"
    "Do'stlarni taklif qilish - ref</code>"
)


@router.callback_query(F.data == "adm:broadcast")
async def start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.broadcast_message)
    await show(
        call,
        "📢 <b>E'lon yuborish</b>\n\n"
        "Foydalanuvchilarga yuboriladigan xabarni yuboring: matn, rasm, video, audio, "
        "fayl, ovozli xabar, stiker, so'rovnoma — istalgan turdagi xabar bo'lishi mumkin.",
        cancel_kb(),
    )


@router.message(AdminStates.broadcast_message)
async def got_message(message: Message, state: FSMContext) -> None:
    if message.media_group_id:
        await message.answer("⚠️ Albom (media group) qo'llab-quvvatlanmaydi — bitta media yuboring.")
        return
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id, buttons=None)
    await state.set_state(AdminStates.broadcast_buttons)
    await message.answer(
        "Xabar ostiga tugma qo'shasizmi?",
        reply_markup=ikb(
            [
                [("➕ Tugma qo'shish", "bc:add_buttons")],
                [("➡️ Tugmasiz davom etish", "bc:preview")],
                [("❌ Bekor qilish", "adm:cancel")],
            ]
        ),
    )


@router.callback_query(AdminStates.broadcast_buttons, F.data == "bc:add_buttons")
async def ask_buttons(call: CallbackQuery) -> None:
    await call.message.answer(BUTTONS_HELP, reply_markup=cancel_kb())
    await call.answer()


@router.message(AdminStates.broadcast_buttons, F.text)
async def got_buttons(message: Message, state: FSMContext, db: Database, bot: Bot, bot_username: str) -> None:
    try:
        rows = await parse_buttons(message.text, db)
    except ButtonParseError as exc:
        await message.answer(f"⚠️ {exc}\n\nQaytadan yuboring.", reply_markup=cancel_kb())
        return
    await state.update_data(buttons=[[asdict(b) for b in row] for row in rows])
    await _preview(message.chat.id, state, bot, bot_username)


@router.callback_query(AdminStates.broadcast_buttons, F.data == "bc:preview")
async def preview_no_buttons(call: CallbackQuery, state: FSMContext, bot: Bot, bot_username: str) -> None:
    await call.answer()
    await _preview(call.message.chat.id, state, bot, bot_username)


def _restore(data: dict) -> list[list[ButtonSpec]] | None:
    raw = data.get("buttons")
    return [[ButtonSpec(**b) for b in row] for row in raw] if raw else None


async def _preview(chat_id: int, state: FSMContext, bot: Bot, bot_username: str) -> None:
    data = await state.get_data()
    buttons = _restore(data)
    await bot.send_message(chat_id, "👁 <b>Ko'rinishi:</b>")
    await bot.copy_message(
        chat_id, data["chat_id"], data["message_id"],
        reply_markup=build_markup(buttons, bot_username, chat_id),
    )
    await state.set_state(AdminStates.broadcast_confirm)
    await bot.send_message(
        chat_id,
        "Barcha foydalanuvchilarga yuborilsinmi?",
        reply_markup=ikb([[("✅ Yuborish", "bc:send"), ("❌ Bekor qilish", "adm:cancel")]]),
    )


@router.callback_query(AdminStates.broadcast_confirm, F.data == "bc:send")
async def send(call: CallbackQuery, state: FSMContext, bot: Bot, db: Database, bot_username: str) -> None:
    data = await state.get_data()
    await state.clear()
    buttons = _restore(data)
    total = len(await db.all_user_ids())
    await show(call, f"🚀 E'lon yuborish boshlandi... (<b>{total}</b> ta foydalanuvchi)")
    status = call.message

    async def progress(result: BroadcastResult, done: int) -> None:
        try:
            await status.edit_text(
                f"🚀 Yuborilmoqda: <b>{done}/{result.total}</b>\n"
                f"✅ {result.sent} | 🚫 {result.blocked} | ⚠️ {result.failed}"
            )
        except Exception:  # noqa: BLE001
            pass

    async def runner() -> None:
        try:
            result = await broadcast_copy(
                bot, db, data["chat_id"], data["message_id"], buttons, bot_username, progress
            )
        except Exception:  # noqa: BLE001
            log.exception("E'lon yuborishda xato")
            await bot.send_message(call.from_user.id, "⚠️ E'lon yuborishda xatolik yuz berdi.")
            return
        await bot.send_message(
            call.from_user.id,
            "✅ <b>E'lon yuborildi!</b>\n\n"
            f"👥 Jami: {result.total}\n"
            f"✅ Yetkazildi: {result.sent}\n"
            f"🚫 Botni bloklagan: {result.blocked}\n"
            f"⚠️ Xatolik: {result.failed}",
        )

    # Uzoq jarayon — fon rejimida, bot boshqa so'rovlarga javob berishda davom etadi.
    asyncio.create_task(runner())
