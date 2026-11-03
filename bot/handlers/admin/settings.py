"""Bot sozlamalari va adminlarni boshqarish."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import Database
from bot.handlers.admin.common import AdminStates, IsAdmin, show
from bot.keyboards import cancel_kb, ikb

router = Router(name="admin_settings")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

TOGGLES = {
    "bot_enabled": "🤖 Bot ishlashi (foydalanuvchilar uchun)",
    "check_sub_on_draw": "🔎 G'olibni tanlashda obunani qayta tekshirish",
    "announce_results": "📣 Natijalarni barcha foydalanuvchilarga e'lon qilish",
}


def _mark(value: bool) -> str:
    return "✅" if value else "❌"


async def render(call: CallbackQuery, db: Database) -> None:
    lines = [f"{_mark(db.get_bool(k))} {label}" for k, label in TOGGLES.items()]
    text = "⚙️ <b>Bot sozlamalari</b>\n\n" + "\n".join(lines) + (
        "\n\nℹ️ Start xabari va boshqa barcha matnlar «📝 Bot matnlari» bo'limida."
    )
    rows = [[(f"{_mark(db.get_bool(k))} {label}", f"st:t:{k}")] for k, label in TOGGLES.items()]
    rows.append([("📝 Bot matnlari", "adm:texts")])
    rows.append([("⬅️ Orqaga", "adm:main")])
    await show(call, text, ikb(rows))


@router.callback_query(F.data == "adm:settings")
async def settings_menu(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await render(call, db)


@router.callback_query(F.data.startswith("st:t:"))
async def toggle(call: CallbackQuery, db: Database) -> None:
    key = call.data.split(":", 2)[2]
    if key in TOGGLES:
        await db.set(key, not db.get_bool(key))
    await render(call, db)


# -------------------------------------------------------------------------- adminlar
async def render_admins(call: CallbackQuery, db: Database, config: Config) -> None:
    lines = [f"👑 <code>{uid}</code> (asosiy, .env)" for uid in sorted(config.admin_ids)]
    lines += [f"👮 <code>{uid}</code>" for uid in sorted(db.db_admins - config.admin_ids)]
    rows = []
    if call.from_user.id in config.admin_ids:
        rows = [[(f"🗑 {uid}", f"ad:del:{uid}")] for uid in sorted(db.db_admins - config.admin_ids)]
        rows.append([("➕ Admin qo'shish", "ad:add")])
    rows.append([("⬅️ Orqaga", "adm:main")])
    note = "" if call.from_user.id in config.admin_ids else "\n\nℹ️ Adminlarni faqat asosiy adminlar boshqaradi."
    await show(call, "👮 <b>Adminlar</b>\n\n" + "\n".join(lines) + note, ikb(rows))


@router.callback_query(F.data == "adm:admins")
async def admins_menu(call: CallbackQuery, db: Database, config: Config, state: FSMContext) -> None:
    await state.clear()
    await render_admins(call, db, config)


@router.callback_query(F.data.startswith("ad:del:"))
async def delete_admin(call: CallbackQuery, db: Database, config: Config) -> None:
    if call.from_user.id not in config.admin_ids:
        await call.answer("Ruxsat yo'q", show_alert=True)
        return
    await db.remove_admin(int(call.data.split(":")[2]))
    await render_admins(call, db, config)


@router.callback_query(F.data == "ad:add")
async def ask_admin(call: CallbackQuery, state: FSMContext, config: Config) -> None:
    if call.from_user.id not in config.admin_ids:
        await call.answer("Ruxsat yo'q", show_alert=True)
        return
    await state.set_state(AdminStates.admin_add)
    await show(
        call,
        "➕ Yangi adminning Telegram ID sini yuboring yoki uning xabarini forward qiling.\n"
        "(Foydalanuvchi avval botga /start bosgan bo'lishi kerak.)",
        cancel_kb(),
    )


@router.message(AdminStates.admin_add)
async def got_admin(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if message.from_user.id not in config.admin_ids:
        await state.clear()
        return
    origin_user = getattr(message.forward_origin, "sender_user", None) if message.forward_origin else None
    if origin_user:
        user_id = origin_user.id
    elif message.text and message.text.strip().isdigit():
        user_id = int(message.text.strip())
    else:
        await message.answer("⚠️ Raqamli ID yuboring.", reply_markup=cancel_kb())
        return
    user = await db.get_user(user_id)
    if not user:
        await message.answer("⚠️ Bu foydalanuvchi botda topilmadi.", reply_markup=cancel_kb())
        return
    await db.add_admin(user_id)
    await state.clear()
    await message.answer(
        f"✅ {html.escape(user.full_name)} (<code>{user_id}</code>) admin qilindi.",
        reply_markup=ikb([[("👮 Adminlar", "adm:admins"), ("🏠 Panel", "adm:main")]]),
    )
