"""Admin panel: bosh menyu va statistika."""
from __future__ import annotations

import html

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import Database
from bot.handlers.admin.common import IsAdmin, show
from bot.keyboards import ADMIN_BUTTON, admin_main_kb, back_kb
from bot.services.contest import draw_at_text
from bot.services.export import build_users_file

router = Router(name="admin_panel")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

PANEL_TEXT = "⚙️ <b>Admin panel</b>\n\nKerakli bo'limni tanlang:"


@router.message(Command("admin"))
@router.message(F.text == ADMIN_BUTTON)
async def open_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(PANEL_TEXT, reply_markup=admin_main_kb())


@router.callback_query(F.data == "adm:main")
async def main(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(call, PANEL_TEXT, admin_main_kb())


@router.callback_query(F.data == "adm:cancel")
async def cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show(call, "❌ Bekor qilindi.\n\n" + PANEL_TEXT, admin_main_kb())


@router.callback_query(F.data == "adm:close")
async def close(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.delete()
    await call.answer()


async def channels_stats(bot: Bot, db: Database) -> str:
    channels = await db.channels()
    if not channels:
        return "📡 Majburiy kanallar: <b>yo'q</b>"
    joins = await db.join_stats()
    bases = await db.channel_base_counts()
    lines = [f"📡 <b>Majburiy kanallar</b> ({len(channels)} ta):"]
    for ch in channels:
        try:
            members = await bot.get_chat_member_count(ch.chat_id)
        except TelegramAPIError:
            members = None
        base = bases.get(ch.chat_id)
        if base is None and members is not None:
            # Eski kanallar uchun hisob shu paytdan boshlanadi
            await db.set_channel_base(ch.chat_id, members)
            base = members
        total, today = joins.get(ch.chat_id, (0, 0))
        line = f"\n<b>{html.escape(ch.title)}</b>\n"
        line += f"• Obunachilar: <b>{members if members is not None else '?'}</b>"
        if members is not None and base is not None:
            line += f" ({members - base:+d} hisob boshlangandan beri)"
        line += f"\n• Bot orqali obuna bo'ldi: <b>{total}</b> (bugun: {today})"
        lines.append(line)
    return "\n".join(lines)


@router.callback_query(F.data == "adm:stats")
async def stats(call: CallbackQuery, bot: Bot, db: Database, config: Config) -> None:
    s = await db.stats()
    state = "🟢 Faol" if db.get_bool("contest_active") else (
        "🏁 Yakunlangan" if db.get_bool("contest_drawn") else "⏸ To'xtatilgan"
    )
    text = (
        "📊 <b>Statistika</b>\n\n"
        f"👤 Jami foydalanuvchilar: <b>{s['users']}</b>\n"
        f"✅ Faol: <b>{s['active']}</b>\n"
        f"🚫 Botni bloklagan: <b>{s['blocked']}</b>\n"
        f"🆕 Bugun qo'shilgan: <b>{s['today']}</b>\n\n"
        f"🔥 <b>Faol foydalanuvchilar</b> (botdan foydalanganlar):\n"
        f"• Oxirgi 24 soat: <b>{s['dau']}</b>\n"
        f"• Oxirgi 7 kun: <b>{s['wau']}</b>\n"
        f"• Oxirgi 30 kun (oylik): <b>{s['mau']}</b>\n\n"
        f"🎯 <b>Konkurs #{db.contest_id}</b> — {state}\n"
        f"👥 Tasdiqlangan takliflar: <b>{s['refs_total']}</b>\n"
        f"⏳ Obunani kutayotgan takliflar: <b>{s['refs_pending']}</b>\n"
        f"🎲 Random qozonda: <b>{s['pool']}</b> kishi\n"
        f"📅 G'oliblar sanasi: <b>{draw_at_text(db, config)}</b>\n\n"
        + await channels_stats(bot, db)
    )
    await show(call, text, back_kb())


@router.callback_query(F.data == "adm:export")
async def export_users(call: CallbackQuery, db: Database, config: Config) -> None:
    await call.answer("⏳ Fayl tayyorlanmoqda...")
    file, total = await build_users_file(db, config)
    await call.message.answer_document(
        file,
        caption=f"👥 Jami: {total} ta foydalanuvchi\n\nExcel'da yoki Google Sheets'da "
        "(Fayl → Import → Yuklash) ochiladi.",
    )
