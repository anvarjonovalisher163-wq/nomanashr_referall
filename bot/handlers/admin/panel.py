"""Admin panel: bosh menyu va statistika."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import Database
from bot.handlers.admin.common import IsAdmin, show
from bot.keyboards import Btn, admin_main_kb, back_kb
from bot.services.contest import draw_at_text

router = Router(name="admin_panel")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

PANEL_TEXT = "⚙️ <b>Admin panel</b>\n\nKerakli bo'limni tanlang:"


@router.message(Command("admin"))
@router.message(F.text == Btn.ADMIN)
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


@router.callback_query(F.data == "adm:stats")
async def stats(call: CallbackQuery, db: Database, config: Config) -> None:
    s = await db.stats()
    channels = len(await db.channels())
    state = "🟢 Faol" if db.get_bool("contest_active") else (
        "🏁 Yakunlangan" if db.get_bool("contest_drawn") else "⏸ To'xtatilgan"
    )
    text = (
        "📊 <b>Statistika</b>\n\n"
        f"👤 Jami foydalanuvchilar: <b>{s['users']}</b>\n"
        f"✅ Faol: <b>{s['active']}</b>\n"
        f"🚫 Botni bloklagan: <b>{s['blocked']}</b>\n"
        f"🆕 Bugun qo'shilgan: <b>{s['today']}</b>\n\n"
        f"🎯 <b>Konkurs #{db.contest_id}</b> — {state}\n"
        f"👥 Tasdiqlangan takliflar: <b>{s['refs_total']}</b>\n"
        f"⏳ Obunani kutayotgan takliflar: <b>{s['refs_pending']}</b>\n"
        f"🎲 Random qozonda: <b>{s['pool']}</b> kishi\n"
        f"📅 G'oliblar sanasi: <b>{draw_at_text(db, config)}</b>\n\n"
        f"📡 Majburiy kanallar: <b>{channels}</b> ta"
    )
    await show(call, text, back_kb())
