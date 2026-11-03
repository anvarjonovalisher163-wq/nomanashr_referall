"""Admin panel: botdan foydalanuvchiga boradigan har bir matn va tugmani o'zgartirish."""
from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.db import Database
from bot.handlers.admin.common import AdminStates, IsAdmin, show
from bot.keyboards import ADMIN_BUTTON, cancel_kb, ikb

router = Router(name="admin_texts")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

PER_PAGE = 8
KIND_NAMES = {
    "html": "xabar (qalin, kursiv, havolalar saqlanadi)",
    "plain": "oddiy matn (formatlashsiz)",
    "button": "tugma yozuvi",
    "alert": "tugma bosilganda chiqadigan oyna",
}


def _page_of(key: str) -> int:
    return texts.ORDER.index(key) // PER_PAGE


async def render_list(call: CallbackQuery, db: Database, page: int) -> None:
    pages = (len(texts.ORDER) + PER_PAGE - 1) // PER_PAGE
    page = max(0, min(page, pages - 1))
    keys = texts.ORDER[page * PER_PAGE:(page + 1) * PER_PAGE]
    rows = [[(("✏️ " if texts.is_custom(db, k) else "") + texts.TEXTS[k].title, f"tx:e:{k}")] for k in keys]
    nav = []
    if page > 0:
        nav.append(("⬅️", f"tx:p:{page - 1}"))
    nav.append((f"{page + 1}/{pages}", f"tx:p:{page}"))
    if page < pages - 1:
        nav.append(("➡️", f"tx:p:{page + 1}"))
    rows.append(nav)
    rows.append([("🏠 Admin panel", "adm:main")])
    await show(
        call,
        "📝 <b>Bot matnlari</b>\n\n"
        "Botdan foydalanuvchilarga boradigan har bir xabar va tugma yozuvini shu yerdan o'zgartirasiz.\n"
        "✏️ — o'zgartirilgan matnlar.",
        ikb(rows),
    )


@router.callback_query(F.data == "adm:texts")
async def texts_menu(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await render_list(call, db, 0)


@router.callback_query(F.data.startswith("tx:p:"))
async def texts_page(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await render_list(call, db, int(call.data.split(":")[2]))


def _current_view(db: Database, key: str) -> str:
    d = texts.TEXTS[key]
    current = texts.get(db, key)
    shown = current if d.kind == "html" else f"<code>{html.escape(current)}</code>"
    placeholders = ", ".join(f"<code>{{{p}}}</code>" for p in d.placeholders) or "yo'q"
    return (
        f"📝 <b>{html.escape(d.title)}</b>\n"
        f"Turi: {KIND_NAMES[d.kind]}\n"
        f"O'zgaruvchilar: {placeholders}\n"
        f"Holat: {'✏️ o‘zgartirilgan' if texts.is_custom(db, key) else 'standart'}\n\n"
        f"<b>Joriy matn:</b>\n{shown}"
    )


async def render_text(call: CallbackQuery, db: Database, key: str) -> None:
    rows = [[("✏️ O'zgartirish", f"tx:w:{key}")]]
    if texts.is_custom(db, key):
        rows.append([("♻️ Standartga qaytarish", f"tx:r:{key}")])
    rows.append([("⬅️ Orqaga", f"tx:p:{_page_of(key)}")])
    await show(call, _current_view(db, key), ikb(rows))


@router.callback_query(F.data.startswith("tx:e:"))
async def open_text(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    key = call.data.split(":", 2)[2]
    if key not in texts.TEXTS:
        await call.answer("Topilmadi", show_alert=True)
        return
    await render_text(call, db, key)


@router.callback_query(F.data.startswith("tx:r:"))
async def reset_text(call: CallbackQuery, db: Database) -> None:
    key = call.data.split(":", 2)[2]
    if key in texts.TEXTS:
        await db.delete_setting(key)
        await call.answer("♻️ Standart matn tiklandi")
        await render_text(call, db, key)


@router.callback_query(F.data.startswith("tx:w:"))
async def ask_text(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 2)[2]
    d = texts.TEXTS.get(key)
    if not d:
        return
    await state.set_state(AdminStates.edit_text)
    await state.update_data(text_key=key)
    hint = ""
    if d.placeholders:
        hint = "\n\nQuyidagi o'zgaruvchilar avtomatik almashtiriladi: " + ", ".join(
            f"<code>{{{p}}}</code>" for p in d.placeholders
        )
    if d.kind == "html":
        hint += "\n\nQalin, kursiv, havola kabi formatlash saqlanadi."
    await show(
        call,
        f"✏️ <b>{html.escape(d.title)}</b> uchun yangi matnni yuboring "
        f"(eng ko'pi {texts.LIMITS[d.kind]} belgi).{hint}",
        cancel_kb(),
    )


@router.message(AdminStates.edit_text, F.text)
async def save_text(message: Message, state: FSMContext, db: Database) -> None:
    key = (await state.get_data()).get("text_key")
    d = texts.TEXTS.get(key or "")
    if not d:
        await state.clear()
        return
    value = message.html_text if d.kind == "html" else message.text.strip()
    limit = texts.LIMITS[d.kind]
    if not value or len(value) > limit:
        await message.answer(f"⚠️ Matn 1–{limit} belgi bo'lishi kerak. Qaytadan yuboring.", reply_markup=cancel_kb())
        return
    if d.kind == "button":
        if "\n" in value:
            await message.answer("⚠️ Tugma yozuvi bitta qatorda bo'lishi kerak.", reply_markup=cancel_kb())
            return
        if key in texts.MENU_BUTTONS:
            others = {texts.get(db, k) for k in texts.MENU_BUTTONS if k != key} | {ADMIN_BUTTON}
            if value in others:
                await message.answer("⚠️ Bu yozuv boshqa menyu tugmasida bor. Boshqasini yozing.", reply_markup=cancel_kb())
                return

    await db.set(key, value)
    await state.clear()
    note = ""
    if key in texts.MENU_BUTTONS:
        note = "\n\nℹ️ Foydalanuvchilar yangi tugmani /start bosganda yoki botga istalgan xabar yozganda ko'radi."
    missing = [p for p in d.placeholders if "{" + p + "}" not in value]
    if missing:
        note += "\n\n⚠️ Matnda ishlatilmagan o'zgaruvchilar: " + ", ".join(f"<code>{{{p}}}</code>" for p in missing)
    await message.answer(
        f"✅ Saqlandi.{note}",
        reply_markup=ikb([[("📝 Ko'rish", f"tx:e:{key}"), ("📋 Ro'yxat", f"tx:p:{_page_of(key)}")]]),
    )
