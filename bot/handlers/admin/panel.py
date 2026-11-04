"""Admin panel: bosh menyu va statistika."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import csv
import io
from datetime import datetime

from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import Config
from bot.db import Database
from bot.handlers.admin.common import IsAdmin, show
from bot.keyboards import ADMIN_BUTTON, admin_main_kb, back_kb
from bot.services.contest import draw_at_text

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
        f"🔥 <b>Faol foydalanuvchilar</b> (botdan foydalanganlar):\n"
        f"• Oxirgi 24 soat: <b>{s['dau']}</b>\n"
        f"• Oxirgi 7 kun: <b>{s['wau']}</b>\n"
        f"• Oxirgi 30 kun (oylik): <b>{s['mau']}</b>\n\n"
        f"🎯 <b>Konkurs #{db.contest_id}</b> — {state}\n"
        f"👥 Tasdiqlangan takliflar: <b>{s['refs_total']}</b>\n"
        f"⏳ Obunani kutayotgan takliflar: <b>{s['refs_pending']}</b>\n"
        f"🎲 Random qozonda: <b>{s['pool']}</b> kishi\n"
        f"📅 G'oliblar sanasi: <b>{draw_at_text(db, config)}</b>\n\n"
        f"📡 Majburiy kanallar: <b>{channels}</b> ta"
    )
    await show(call, text, back_kb())


def _local(value: str | None, config: Config) -> str:
    try:
        return datetime.fromisoformat(value).astimezone(config.tz).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return value or ""


@router.callback_query(F.data == "adm:export")
async def export_users(call: CallbackQuery, db: Database, config: Config) -> None:
    await call.answer("⏳ Fayl tayyorlanmoqda...")
    rows = await db.export_users()
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")  # ";" — Excel'da ustunlar to'g'ri ajraladi
    writer.writerow([
        "ID", "Ism", "Username", "Qo'shilgan vaqt", "Taklif qilgan (ID)", "Taklif qilgan (ism)",
        "Taklif qilgan (username)", "Takliflari soni", "Botni bloklagan", "Oxirgi faollik",
    ])
    for r in rows:
        try:
            joined = datetime.fromisoformat(r["created_at"]).astimezone(config.tz).strftime("%d.%m.%Y %H:%M")
        except (TypeError, ValueError):
            joined = r["created_at"] or ""
        writer.writerow([
            r["user_id"], r["full_name"] or "", f"@{r['username']}" if r["username"] else "", joined,
            r["referrer_id"] or "", r["referrer_name"] or "",
            f"@{r['referrer_username']}" if r["referrer_username"] else "",
            r["refs"], "ha" if r["is_blocked"] else "yo'q", _local(r["last_seen"], config),
        ])
    data = buffer.getvalue().encode("utf-8-sig")
    await call.message.answer_document(
        BufferedInputFile(data, filename=f"foydalanuvchilar_{datetime.now(config.tz):%Y-%m-%d_%H-%M}.csv"),
        caption=f"👥 Jami: {len(rows)} ta foydalanuvchi\n\nExcel'da yoki Google Sheets'da "
        "(Fayl → Import → Yuklash) ochiladi.",
    )
