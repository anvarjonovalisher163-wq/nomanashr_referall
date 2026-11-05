"""Bot sozlamalari va adminlarni boshqarish."""
from __future__ import annotations

import html

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Config
from bot.db import Database
from bot.handlers.admin.common import AdminStates, IsAdmin, show
from bot.services.export import INTERVAL_CHOICES, interval_label
from bot.keyboards import cancel_kb, ikb

router = Router(name="admin_settings")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

TOGGLES = {
    "bot_enabled": "🤖 Bot ishlashi (foydalanuvchilar uchun)",
    "ref_requires_sub": "👥 Taklif qilingan do'st ham kanallarga obuna bo'lishi shart",
    "check_sub_on_draw": "🔎 G'olibni tanlashda obunani qayta tekshirish",
    "announce_results": "📣 Natijalarni barcha foydalanuvchilarga e'lon qilish",
    "notify_new_users": "🆕 Har bir yangi foydalanuvchi haqida xabar",
}


def _mark(value: bool) -> str:
    return "✅" if value else "❌"


async def render(call: CallbackQuery, db: Database) -> None:
    lines = [f"{_mark(db.get_bool(k))} {label}" for k, label in TOGGLES.items()]
    text = "⚙️ <b>Bot sozlamalari</b>\n\n" + "\n".join(lines) + (
        "\n\nℹ️ Start xabari va boshqa barcha matnlar «📝 Bot matnlari» bo'limida."
    )
    rows = [[(f"{_mark(db.get_bool(k))} {label}", f"st:t:{k}")] for k, label in TOGGLES.items()]
    log_chat = db.get("log_chat_id")
    rows.append([(f"📋 Log kanal: {log_chat or 'yo‘q (adminlarga)'}", "st:log")])
    if log_chat:
        rows.append([("🗑 Log kanalni o'chirish", "st:log_del")])
    rows.append([(f"📥 Excel avtomatik: {interval_label(db.get_int('export_interval'))}", "st:exp")])
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


@router.callback_query(F.data == "st:exp")
async def export_menu(call: CallbackQuery, db: Database) -> None:
    current = db.get_int("export_interval")
    rows, row = [], []
    for minutes in INTERVAL_CHOICES:
        mark = "✅ " if minutes == current else ""
        row.append((mark + interval_label(minutes), f"st:exp:{minutes}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("⬅️ Orqaga", "adm:settings")])
    target = "log kanalga" if db.get("log_chat_id") else "asosiy adminlarga (log kanal ulanmagan)"
    await show(
        call,
        "📥 <b>Foydalanuvchilar ro'yxatini avtomatik yuborish</b>\n\n"
        f"Hozir: <b>{interval_label(current)}</b>\n"
        f"Fayl {target} yuboriladi.\n\nQanchalik tez-tez yuborilsin?",
        ikb(rows),
    )


@router.callback_query(F.data.startswith("st:exp:"))
async def export_set(call: CallbackQuery, db: Database) -> None:
    minutes = int(call.data.split(":")[2])
    if minutes in INTERVAL_CHOICES:
        await db.set("export_interval", minutes)
        await db.set("export_last_at", "")  # yangi oraliq darhol (1 daqiqa ichida) kuchga kiradi
        await call.answer(f"✅ {interval_label(minutes).capitalize()}")
    await export_menu(call, db)


@router.callback_query(F.data == "st:log")
async def ask_log_chat(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.set_log_chat)
    await show(
        call,
        "📋 <b>Log kanal</b>\n\n"
        "Yangi foydalanuvchilar haqidagi xabarlar shu kanal/guruhga boradi (ko'p odam qo'shilganda "
        "shaxsiy chatingiz to'lib ketmasligi uchun).\n\n"
        "1. Yopiq kanal yoki guruh yarating va botni u yerga <b>admin</b> qiling.\n"
        "2. Kanaldan istalgan postni shu yerga <b>forward</b> qiling yoki ID sini (<code>-100...</code>) yuboring.",
        cancel_kb(),
    )


@router.message(AdminStates.set_log_chat)
async def set_log_chat(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    origin_chat = getattr(message.forward_origin, "chat", None) if message.forward_origin else None
    raw = str(origin_chat.id) if origin_chat else (message.text or "").strip()
    if not raw.lstrip("-").isdigit() and not raw.startswith("@"):
        await message.answer("⚠️ Kanal ID sini yuboring yoki postini forward qiling.", reply_markup=cancel_kb())
        return
    try:
        sent = await bot.send_message(int(raw) if raw.lstrip("-").isdigit() else raw, "✅ Log kanal ulandi.")
    except TelegramAPIError as exc:
        await message.answer(
            f"⚠️ Bot bu chatga yoza olmadi — botni admin qiling.\n<code>{html.escape(str(exc))}</code>",
            reply_markup=cancel_kb(),
        )
        return
    await db.set("log_chat_id", sent.chat.id)
    await state.clear()
    await message.answer(
        f"✅ Log kanal saqlandi: <code>{sent.chat.id}</code>",
        reply_markup=ikb([[("⚙️ Sozlamalar", "adm:settings"), ("🏠 Panel", "adm:main")]]),
    )


@router.callback_query(F.data == "st:log_del")
async def delete_log_chat(call: CallbackQuery, db: Database) -> None:
    await db.set("log_chat_id", "")
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
