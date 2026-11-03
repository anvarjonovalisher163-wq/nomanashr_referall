"""Admin panel: botdan foydalanuvchiga boradigan har bir matn, media va tugmani o'zgartirish."""
from __future__ import annotations

import html

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import texts
from bot.db import Database
from bot.handlers.admin.broadcast import BUTTONS_HELP
from bot.handlers.admin.common import AdminStates, IsAdmin, show
from bot.keyboards import ADMIN_BUTTON, cancel_kb, ikb
from bot.services import rich
from bot.services.buttons import ButtonParseError, parse_buttons

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


def _marks(db: Database, key: str) -> str:
    mark = "✏️ " if texts.is_custom(db, key) else ""
    if rich.get_media(db, key):
        mark += "🖼"
    if rich.get_buttons(db, key):
        mark += "🔘"
    return mark + (" " if mark and not mark.endswith(" ") else "")


async def render_list(call: CallbackQuery, db: Database, page: int) -> None:
    pages = (len(texts.ORDER) + PER_PAGE - 1) // PER_PAGE
    page = max(0, min(page, pages - 1))
    keys = texts.ORDER[page * PER_PAGE:(page + 1) * PER_PAGE]
    rows = [[(_marks(db, k) + texts.TEXTS[k].title, f"tx:e:{k}")] for k in keys]
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
        "Botdan foydalanuvchilarga boradigan har bir xabar va tugma yozuvini shu yerdan o'zgartirasiz. "
        "Alohida xabarlarga <b>media</b> (rasm, video, GIF, fayl) va <b>tugmalar</b> ham qo'shish mumkin.\n\n"
        "✏️ — o'zgartirilgan, 🖼 — media bor, 🔘 — tugma bor.",
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
    lines = [
        f"📝 <b>{html.escape(d.title)}</b>",
        f"Turi: {KIND_NAMES[d.kind]}",
        f"O'zgaruvchilar: {placeholders}",
        f"Holat: {'✏️ o‘zgartirilgan' if texts.is_custom(db, key) else 'standart'}",
    ]
    if d.rich:
        media = rich.get_media(db, key)
        buttons = rich.get_buttons(db, key)
        lines.append(f"Media: {rich.MEDIA_NAMES[media[0]] if media else 'yo‘q'}")
        lines.append(f"Tugmalar: {sum(len(r) for r in buttons)} ta" if buttons else "Tugmalar: yo‘q")
    if key == "winners_header":
        lines.append("\nℹ️ Media va tugmalar butun g'oliblar ro'yxati xabariga biriktiriladi.")
    return "\n".join(lines) + f"\n\n<b>Joriy matn:</b>\n{shown}"


async def render_text(call: CallbackQuery, db: Database, key: str) -> None:
    d = texts.TEXTS[key]
    rows = [[("✏️ Matnni o'zgartirish", f"tx:w:{key}")]]
    if d.rich:
        media = rich.get_media(db, key)
        rows.append([("🖼 Media almashtirish" if media else "🖼 Media qo'shish", f"tx:w:{key}")])
        if media:
            rows[-1].append(("🗑 Mediani o'chirish", f"tx:dm:{key}"))
        has_buttons = bool(rich.get_buttons(db, key))
        rows.append([("🔘 Tugmalarni almashtirish" if has_buttons else "🔘 Tugma qo'shish", f"tx:b:{key}")])
        if has_buttons:
            rows[-1].append(("🗑 Tugmalarni o'chirish", f"tx:db:{key}"))
        rows.append([("👁 Ko'rish (sinov)", f"tx:v:{key}")])
    if texts.is_custom(db, key):
        rows.append([("♻️ Standartga qaytarish", f"tx:r:{key}")])
    rows.append([("⬅️ Orqaga", f"tx:p:{_page_of(key)}")])
    await show(call, _current_view(db, key), ikb(rows))


def _key(call: CallbackQuery) -> str | None:
    key = call.data.split(":", 2)[2]
    return key if key in texts.TEXTS else None


@router.callback_query(F.data.startswith("tx:e:"))
async def open_text(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    key = _key(call)
    if not key:
        await call.answer("Topilmadi", show_alert=True)
        return
    await render_text(call, db, key)


@router.callback_query(F.data.startswith("tx:r:"))
async def reset_text(call: CallbackQuery, db: Database) -> None:
    key = _key(call)
    if key:
        for k in (key, rich.media_key(key), rich.buttons_key(key)):
            await db.delete_setting(k)
        await call.answer("♻️ Standart holat tiklandi")
        await render_text(call, db, key)


@router.callback_query(F.data.startswith("tx:dm:"))
async def delete_media(call: CallbackQuery, db: Database) -> None:
    key = _key(call)
    if key:
        await db.delete_setting(rich.media_key(key))
        await call.answer("🗑 Media o'chirildi")
        await render_text(call, db, key)


@router.callback_query(F.data.startswith("tx:db:"))
async def delete_buttons(call: CallbackQuery, db: Database) -> None:
    key = _key(call)
    if key:
        await db.delete_setting(rich.buttons_key(key))
        await call.answer("🗑 Tugmalar o'chirildi")
        await render_text(call, db, key)


@router.callback_query(F.data.startswith("tx:v:"))
async def preview(call: CallbackQuery, bot: Bot, db: Database) -> None:
    key = _key(call)
    if not key:
        return
    await call.answer()
    await bot.send_message(call.from_user.id, "👁 <b>Foydalanuvchi shunday ko'radi</b> (o'zgaruvchilar almashtirilmagan):")
    await rich.send_rich(bot, call.from_user.id, db, key)
    await bot.send_message(call.from_user.id, "⬆️", reply_markup=ikb([[("⬅️ Matnga qaytish", f"tx:e:{key}")]]))


# --------------------------------------------------------------------- matn / media
@router.callback_query(F.data.startswith("tx:w:"))
async def ask_text(call: CallbackQuery, state: FSMContext) -> None:
    key = _key(call)
    if not key:
        return
    d = texts.TEXTS[key]
    await state.set_state(AdminStates.edit_text)
    await state.update_data(text_key=key)
    hint = ""
    if d.placeholders:
        hint += "\n\nQuyidagi o'zgaruvchilar avtomatik almashtiriladi: " + ", ".join(
            f"<code>{{{p}}}</code>" for p in d.placeholders
        )
    if d.kind == "html":
        hint += "\n\nQalin, kursiv, havola kabi formatlash saqlanadi."
    if d.rich:
        hint += (
            "\n\n🖼 <b>Media qo'shish:</b> rasm, video, GIF, audio yoki faylni yuboring va uning "
            "<b>izohiga</b> (caption) matnni yozing. Faqat matn yuborsangiz — matn o'zgaradi, "
            "oldingi media saqlanib qoladi."
        )
    await show(
        call,
        f"✏️ <b>{html.escape(d.title)}</b> uchun yangi matnni yuboring "
        f"(eng ko'pi {texts.LIMITS[d.kind]} belgi).{hint}",
        cancel_kb(),
    )


def _done_kb(key: str):
    return ikb([
        [("📝 Ko'rish", f"tx:e:{key}"), ("👁 Sinov", f"tx:v:{key}")],
        [("📋 Ro'yxat", f"tx:p:{_page_of(key)}")],
    ])


@router.message(AdminStates.edit_text)
async def save_text(message: Message, state: FSMContext, db: Database) -> None:
    key = (await state.get_data()).get("text_key")
    d = texts.TEXTS.get(key or "")
    if not d:
        await state.clear()
        return

    media = rich.extract_media(message) if d.rich else None
    if media:
        value = message.html_text if message.caption else ""
    elif message.text:
        value = message.html_text if d.kind == "html" else message.text.strip()
    else:
        what = "matn yoki media (rasm, video, GIF, audio, fayl)" if d.rich else "matn"
        await message.answer(f"⚠️ {what.capitalize()} yuboring.", reply_markup=cancel_kb())
        return

    limit = texts.LIMITS[d.kind]
    if len(value) > limit or (not value and not media):
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

    notes = []
    if media:
        await db.set(rich.media_key(key), f"{media[0]}:{media[1]}")
        notes.append(f"🖼 {rich.MEDIA_NAMES[media[0]].capitalize()} biriktirildi.")
    if value:
        await db.set(key, value)
    else:
        notes.append("ℹ️ Izoh yozilmagani uchun matn o'zgarmadi.")
    if media and len(texts.get(db, key)) > rich.CAPTION_LIMIT:
        notes.append(
            f"ℹ️ Matn {rich.CAPTION_LIMIT} belgidan uzun — media va matn ikkita alohida xabar bo'lib boradi."
        )
    await state.clear()

    if key in texts.MENU_BUTTONS:
        notes.append("ℹ️ Foydalanuvchilar yangi tugmani /start bosganda yoki botga istalgan xabar yozganda ko'radi.")
    missing = [p for p in d.placeholders if "{" + p + "}" not in texts.get(db, key)]
    if missing:
        notes.append("⚠️ Matnda ishlatilmagan o'zgaruvchilar: " + ", ".join(f"<code>{{{p}}}</code>" for p in missing))
    await message.answer("✅ Saqlandi." + "".join("\n\n" + n for n in notes), reply_markup=_done_kb(key))


# ------------------------------------------------------------------------ tugmalar
@router.callback_query(F.data.startswith("tx:b:"))
async def ask_buttons(call: CallbackQuery, state: FSMContext) -> None:
    key = _key(call)
    if not key or not texts.TEXTS[key].rich:
        return
    await state.set_state(AdminStates.edit_buttons)
    await state.update_data(text_key=key)
    await show(
        call,
        BUTTONS_HELP + "\n\nℹ️ Bu tugmalar xabardagi mavjud tugmalar (masalan, kanallar ro'yxati) ostiga qo'shiladi.",
        cancel_kb(),
    )


@router.message(AdminStates.edit_buttons, F.text)
async def save_buttons(message: Message, state: FSMContext, db: Database) -> None:
    key = (await state.get_data()).get("text_key")
    if key not in texts.TEXTS:
        await state.clear()
        return
    try:
        rows = await parse_buttons(message.text, db)
    except ButtonParseError as exc:
        await message.answer(f"⚠️ {exc}\n\nQaytadan yuboring.", reply_markup=cancel_kb())
        return
    await db.set(rich.buttons_key(key), rich.dump_buttons(rows))
    await state.clear()
    note = ""
    if key == "welcome_text":
        note = (
            "\n\nℹ️ Telegram bitta xabarga ham menyu, ham inline tugma qo'yishga ruxsat bermaydi, "
            "shuning uchun menyu keyingi qisqa xabar («Noma'lum xabarga javob» matni) bilan yuboriladi."
        )
    await message.answer(f"✅ Tugmalar saqlandi ({sum(len(r) for r in rows)} ta).{note}", reply_markup=_done_kb(key))
