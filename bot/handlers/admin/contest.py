"""Konkursni boshqarish: shartlar, sana, qozon, g'oliblarni aniqlash."""
from __future__ import annotations

import asyncio
import csv
import io
from datetime import datetime

import html

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message

from bot import texts
from bot.config import Config
from bot.db import Database
from bot.handlers.admin.common import AdminStates, IsAdmin, show
from bot.keyboards import cancel_kb, ikb
from bot.services.rich import send_rich
from bot.services.contest import DATE_FORMAT, admin_winners_message, results_text, draw_at_text, parse_date, run_draw

router = Router(name="admin_contest")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _text(db: Database, config: Config) -> str:
    if db.get_bool("contest_drawn"):
        state = "🏁 Yakunlangan (g'oliblar aniqlangan)"
    elif db.get_bool("contest_active"):
        state = "🟢 Faol"
    else:
        state = "⏸ To'xtatilgan"
    required = db.get_int("required_refs")
    pool = await db.pool(db.contest_id, required)
    return (
        f"🎯 <b>Konkurs #{db.contest_id}</b>\n\n"
        f"Holat: {state}\n"
        f"👥 Qozonga kirish uchun takliflar soni (N): <b>{required}</b>\n"
        f"🏆 G'oliblar soni: <b>{db.get_int('winners_count')}</b>\n"
        f"📅 G'oliblarni aniqlash sanasi: <b>{draw_at_text(db, config)}</b>\n"
        f"🎲 Random qozonda: <b>{len(pool)}</b> kishi\n\n"
        f"🎁 Sovg'a matni:\n{texts.get(db, 'prize_text')}"
    )


def _kb(db: Database):
    rows = []
    if not db.get_bool("contest_drawn"):
        if db.get_bool("contest_active"):
            rows.append([("⏸ To'xtatish", "ct:toggle")])
        else:
            rows.append([("▶️ Boshlash", "ct:toggle")])
    rows += [
        [("👥 Takliflar soni (N)", "ct:set:required"), ("🏆 G'oliblar soni", "ct:set:winners")],
        [("📅 Sana", "ct:set:date"), ("🎁 Sovg'a matni", "ct:set:prize")],
        [("📥 Qozon ro'yxati (CSV)", "ct:export")],
    ]
    if db.get_bool("contest_drawn"):
        rows.append([("🏆 G'oliblar", "ct:winners"), ("📢 Kanalga e'lon qilish", "ct:post")])
    else:
        rows.append([("🎲 Hozir g'oliblarni aniqlash", "ct:draw")])
    rows.append([("🔄 Yangi konkurs boshlash", "ct:new")])
    rows.append([("⬅️ Orqaga", "adm:main")])
    return ikb(rows)


async def render(call: CallbackQuery, db: Database, config: Config) -> None:
    await show(call, await _text(db, config), _kb(db))


@router.callback_query(F.data == "adm:contest")
async def contest_menu(call: CallbackQuery, db: Database, config: Config, state: FSMContext) -> None:
    await state.clear()
    await render(call, db, config)


@router.callback_query(F.data == "ct:toggle")
async def toggle(call: CallbackQuery, db: Database, config: Config) -> None:
    if db.get_bool("contest_drawn"):
        await call.answer("Konkurs yakunlangan. Yangi konkurs boshlang.", show_alert=True)
        return
    activate = not db.get_bool("contest_active")
    if activate:
        when = parse_date(db.get("draw_at"), config) if db.get("draw_at") else None
        if not when or when <= datetime.now(config.tz):
            await call.answer("Avval kelajakdagi sanani belgilang (📅 Sana).", show_alert=True)
            return
    await db.set("contest_active", activate)
    await render(call, db, config)


# ----------------------------------------------------------- qiymatlarni o'zgartirish
_PROMPTS = {
    "required": (AdminStates.set_required, "👥 Random qozonga kirish uchun nechta do'st taklif qilish kerak? (son yuboring)"),
    "winners": (AdminStates.set_winners, "🏆 Nechta g'olib tanlansin? (son yuboring)"),
    "date": (
        AdminStates.set_date,
        "📅 G'oliblar aniqlanadigan sana va vaqtni yuboring.\n\n"
        "Format: <code>31.12.2026 20:00</code> yoki <code>2026-12-31 20:00</code>",
    ),
    "prize": (AdminStates.set_prize, "🎁 Sovg'alar haqida matnni yuboring (formatlash saqlanadi)."),
}


@router.callback_query(F.data.startswith("ct:set:"))
async def ask_value(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":")[2]
    new_state, prompt = _PROMPTS[key]
    await state.set_state(new_state)
    await show(call, prompt, cancel_kb())


async def _done(message: Message, state: FSMContext, db: Database, config: Config, note: str) -> None:
    await state.clear()
    await message.answer(f"✅ {note}\n\n" + await _text(db, config), reply_markup=_kb(db))


def _positive_int(text: str | None, limit: int) -> int | None:
    if text and text.strip().isdigit():
        value = int(text.strip())
        if 1 <= value <= limit:
            return value
    return None


@router.message(AdminStates.set_required)
async def set_required(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    value = _positive_int(message.text, 10_000)
    if value is None:
        await message.answer("⚠️ 1 dan 10000 gacha son yuboring.", reply_markup=cancel_kb())
        return
    await db.set("required_refs", value)
    await _done(message, state, db, config, "Takliflar soni saqlandi.")


@router.message(AdminStates.set_winners)
async def set_winners(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    value = _positive_int(message.text, 1_000)
    if value is None:
        await message.answer("⚠️ 1 dan 1000 gacha son yuboring.", reply_markup=cancel_kb())
        return
    await db.set("winners_count", value)
    await _done(message, state, db, config, "G'oliblar soni saqlandi.")


@router.message(AdminStates.set_date)
async def set_date(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    when = parse_date(message.text or "", config)
    if when is None:
        await message.answer("⚠️ Sana noto'g'ri. Misol: <code>31.12.2026 20:00</code>", reply_markup=cancel_kb())
        return
    if when <= datetime.now(config.tz):
        await message.answer("⚠️ Sana kelajakda bo'lishi kerak.", reply_markup=cancel_kb())
        return
    await db.set("draw_at", when.strftime(DATE_FORMAT))
    await _done(message, state, db, config, "Sana saqlandi.")


@router.message(AdminStates.set_prize, F.text)
async def set_prize(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    await db.set("prize_text", message.html_text)
    await _done(message, state, db, config, "Sovg'a matni saqlandi.")


# ------------------------------------------------------------------- qozon / g'oliblar
@router.callback_query(F.data == "ct:export")
async def export_pool(call: CallbackQuery, db: Database) -> None:
    rows = await db.pool_details(db.contest_id, db.get_int("required_refs"))
    if not rows:
        await call.answer("Qozon hozircha bo'sh.", show_alert=True)
        return
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["user_id", "full_name", "username", "referrals"])
    for r in rows:
        writer.writerow([r["user_id"], r["full_name"], r["username"] or "", r["cnt"]])
    data = buffer.getvalue().encode("utf-8-sig")
    await call.message.answer_document(
        BufferedInputFile(data, filename=f"qozon_konkurs_{db.contest_id}.csv"),
        caption=f"🎲 Random qozon: {len(rows)} kishi",
    )
    await call.answer()


@router.callback_query(F.data == "ct:winners")
async def show_winners(call: CallbackQuery, db: Database) -> None:
    text, kb = await admin_winners_message(db, db.contest_id, len(await db.pool(db.contest_id, db.get_int("required_refs"))))
    rows = (kb.inline_keyboard if kb else []) + ikb([[("⬅️ Orqaga", "adm:contest")]]).inline_keyboard
    await show(call, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "ct:draw")
async def confirm_draw(call: CallbackQuery, db: Database) -> None:
    pool = await db.pool(db.contest_id, db.get_int("required_refs"))
    await show(
        call,
        f"🎲 Random qozonda <b>{len(pool)}</b> kishi bor.\n"
        f"Hozir <b>{db.get_int('winners_count')}</b> ta g'olib tasodifiy tanlansinmi?\n\n"
        "⚠️ Bu amalni qaytarib bo'lmaydi, konkurs yakunlanadi.",
        ikb([[("✅ Ha, aniqlash", "ct:draw_yes"), ("❌ Yo'q", "adm:contest")]]),
    )


@router.callback_query(F.data == "ct:draw_yes")
async def do_draw(call: CallbackQuery, bot: Bot, db: Database, config: Config) -> None:
    if db.get_bool("contest_drawn"):
        await call.answer("G'oliblar allaqachon aniqlangan.", show_alert=True)
        return
    await show(call, "⏳ G'oliblar aniqlanmoqda...")
    # E'lonlar fon rejimida ketadi, natija adminlarga alohida xabar qilib yuboriladi.
    asyncio.create_task(run_draw(bot, db, config))


@router.callback_query(F.data == "ct:new")
async def confirm_new(call: CallbackQuery) -> None:
    await show(
        call,
        "🔄 <b>Yangi konkurs</b>\n\nJoriy konkurs arxivlanadi, barcha takliflar hisobi <b>0</b> dan boshlanadi. "
        "Sozlamalar (N, g'oliblar soni, sovg'a matni) saqlanib qoladi, sana esa qayta belgilanadi.\n\nDavom etamizmi?",
        ikb([[("✅ Ha", "ct:new_yes"), ("❌ Yo'q", "adm:contest")]]),
    )


@router.callback_query(F.data == "ct:new_yes")
async def new_contest(call: CallbackQuery, db: Database, config: Config) -> None:
    await db.set("contest_id", db.contest_id + 1)
    await db.set("contest_active", False)
    await db.set("contest_drawn", False)
    await db.set("draw_at", "")
    await call.answer("Yangi konkurs yaratildi. Sanani belgilab, «Boshlash» ni bosing.", show_alert=True)
    await render(call, db, config)


# ----------------------------------------------------------------- kanalga e'lon qilish
@router.callback_query(F.data == "ct:post")
async def post_choose(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    if not db.get_bool("contest_drawn"):
        await call.answer("G'oliblar hali aniqlanmagan.", show_alert=True)
        return
    await state.set_state(AdminStates.post_chat)
    rows = [[(f"📢 {ch.title[:40]}", f"ct:pv:{ch.chat_id}")] for ch in await db.channels()]
    rows.append([("❌ Bekor qilish", "adm:cancel")])
    await show(
        call,
        "📢 <b>G'oliblarni kanalga e'lon qilish</b>\n\n"
        "Kanalni tanlang yoki boshqa kanaldan postni <b>forward</b> qiling / ID sini (<code>-100...</code>) "
        "yoki <code>@username</code> ni yuboring. Bot o'sha kanalda admin bo'lishi kerak.\n\n"
        "ℹ️ Post matni, rasmi va tugmalari «📝 Bot matnlari → G'oliblar sarlavhasi / G'olib qatori / "
        "Natija oxiri» dan olinadi.",
        ikb(rows),
    )


async def _preview(bot: Bot, admin_id: int, db: Database, chat_ref: str) -> None:
    await bot.send_message(admin_id, "👁 <b>Kanalda shunday ko'rinadi:</b>")
    await send_rich(bot, admin_id, db, "winners_header", text=await results_text(db, db.contest_id))
    await bot.send_message(
        admin_id,
        f"Shu post <code>{html.escape(chat_ref)}</code> ga joylansinmi?",
        reply_markup=ikb([[("✅ Joylash", f"ct:po:{chat_ref}"), ("❌ Bekor qilish", "adm:cancel")]]),
    )


@router.callback_query(F.data.startswith("ct:pv:"))
async def post_preview(call: CallbackQuery, bot: Bot, db: Database) -> None:
    await call.answer()
    await _preview(bot, call.from_user.id, db, call.data.split(":", 2)[2])


@router.message(AdminStates.post_chat)
async def post_chat_input(message: Message, bot: Bot, db: Database) -> None:
    origin_chat = getattr(message.forward_origin, "chat", None) if message.forward_origin else None
    raw = str(origin_chat.id) if origin_chat else (message.text or "").strip()
    if raw.startswith("https://t.me/") and "+" not in raw:
        raw = "@" + raw.removeprefix("https://t.me/").strip("/")
    if not (raw.lstrip("-").isdigit() or raw.startswith("@")) or len(raw) > 50:
        await message.answer("⚠️ Kanal ID si, @username yoki forward qilingan post yuboring.", reply_markup=cancel_kb())
        return
    await _preview(bot, message.from_user.id, db, raw)


@router.callback_query(F.data.startswith("ct:po:"))
async def post_publish(call: CallbackQuery, bot: Bot, db: Database, state: FSMContext) -> None:
    raw = call.data.split(":", 2)[2]
    chat: int | str = int(raw) if raw.lstrip("-").isdigit() else raw
    try:
        await send_rich(bot, chat, db, "winners_header", text=await results_text(db, db.contest_id))
    except TelegramAPIError as exc:
        await call.answer()
        await call.message.answer(
            f"⚠️ Joylab bo'lmadi — bot kanalda admin va post yozish huquqiga ega ekanini tekshiring.\n"
            f"<code>{html.escape(str(exc))}</code>"
        )
        return
    await state.clear()
    await show(call, "✅ G'oliblar kanalga e'lon qilindi!", ikb([[("🎯 Konkurs", "adm:contest")]]))
