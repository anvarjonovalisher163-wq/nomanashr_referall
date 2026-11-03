"""Oddiy foydalanuvchi uchun handlerlar."""
from __future__ import annotations

import html

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import Config
from bot.db import Database
from bot.keyboards import Btn, main_menu, subscribe_kb
from bot.services import subscription
from bot.services.buttons import ref_link, share_url
from bot.services.contest import draw_at_text, on_user_verified, user_mention, winners_text

router = Router(name="user")


async def send_welcome(message: Message, db: Database, is_admin: bool, name: str) -> None:
    text = db.get("welcome_text").replace("{name}", html.escape(name))
    await message.answer(text, reply_markup=main_menu(is_admin))


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, is_admin: bool) -> None:
    await send_welcome(message, db, is_admin, message.from_user.full_name)


@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, bot: Bot, db: Database, is_admin: bool) -> None:
    subscription.invalidate(call.from_user.id)
    missing = await subscription.unsubscribed_channels(bot, db, call.from_user.id, use_cache=False)
    if missing:
        await call.answer("❌ Siz hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)
        try:
            await call.message.edit_reply_markup(reply_markup=subscribe_kb(missing))
        except Exception:  # noqa: BLE001 — klaviatura o'zgarmagan bo'lishi mumkin
            pass
        return
    await call.answer("✅ Rahmat! Obuna tasdiqlandi.")
    try:
        await call.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await on_user_verified(bot, db, call.from_user.id)
    await send_welcome(call.message, db, is_admin, call.from_user.full_name)


@router.callback_query(F.data.startswith("alert:"))
async def alert_button(call: CallbackQuery, db: Database) -> None:
    alert_id = call.data.split(":", 1)[1]
    text = await db.get_alert(int(alert_id)) if alert_id.isdigit() else None
    await call.answer(text or "—", show_alert=True)


@router.message(F.text == Btn.REF)
async def my_link(message: Message, db: Database, bot_username: str) -> None:
    link = ref_link(bot_username, message.from_user.id)
    required = db.get_int("required_refs")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="📤 Do'stlarga ulashish",
                url=share_url(link, "Konkursda ishtirok et va sovg'a yut! 🎁"),
            )
        ]]
    )
    await message.answer(
        f"🔗 <b>Sizning shaxsiy taklif havolangiz:</b>\n<code>{link}</code>\n\n"
        f"Havolani do'stlaringizga yuboring. <b>{required}</b> ta do'stingiz botga kirib, "
        f"majburiy kanallarga obuna bo'lsa — siz random qozonga qo'shilasiz! 🎲",
        reply_markup=kb,
    )


@router.message(F.text == Btn.STATS)
async def my_stats(message: Message, db: Database, config: Config) -> None:
    count = await db.ref_count(message.from_user.id)
    required = db.get_int("required_refs")
    if db.get_bool("contest_drawn"):
        status = "🏁 Konkurs yakunlangan"
    elif not db.get_bool("contest_active"):
        status = "⏸ Konkurs hozircha faol emas"
    elif count >= required:
        status = "✅ Siz random qozondasiz!"
    else:
        status = f"⏳ Qozonga kirish uchun yana <b>{required - count}</b> ta do'st taklif qiling"
    await message.answer(
        f"📊 <b>Sizning natijangiz</b>\n\n"
        f"👥 Tasdiqlangan takliflar: <b>{count}</b> / {required}\n"
        f"{status}\n\n"
        f"📅 G'oliblar aniqlanadigan sana: <b>{draw_at_text(db, config)}</b>"
    )


@router.message(F.text == Btn.TOP)
async def top(message: Message, db: Database) -> None:
    rows = await db.top(db.contest_id, 10)
    if not rows:
        await message.answer("🏆 Hozircha reyting bo'sh. Birinchi bo'ling! 🚀")
        return
    lines = [
        f"{i}. {user_mention(r['user_id'], r['full_name'])} — <b>{r['cnt']}</b> ta"
        for i, r in enumerate(rows, start=1)
    ]
    my = await db.ref_count(message.from_user.id)
    await message.answer(
        "🏆 <b>Eng faol ishtirokchilar (TOP-10):</b>\n\n" + "\n".join(lines) + f"\n\nSizda: <b>{my}</b> ta"
    )


@router.message(F.text == Btn.ABOUT)
async def about(message: Message, db: Database, config: Config) -> None:
    state = "🟢 Faol" if db.get_bool("contest_active") else (
        "🏁 Yakunlangan" if db.get_bool("contest_drawn") else "⏸ Faol emas"
    )
    await message.answer(
        f"ℹ️ <b>Konkurs haqida</b>\n\n"
        f"Holat: {state}\n"
        f"👥 Qozonga kirish sharti: <b>{db.get_int('required_refs')}</b> ta do'st taklif qilish\n"
        f"🏆 G'oliblar soni: <b>{db.get_int('winners_count')}</b> ta\n"
        f"📅 G'oliblar aniqlanadigan sana: <b>{draw_at_text(db, config)}</b>\n\n"
        f"{db.get('prize_text')}\n\n"
        f"❗️ Taklif qilingan do'st botga birinchi marta kirgan va barcha majburiy kanallarga "
        f"obuna bo'lgan bo'lishi kerak."
    )


@router.message(F.text == Btn.WINNERS)
async def winners(message: Message, db: Database) -> None:
    if not db.get_bool("contest_drawn"):
        await message.answer("⏳ G'oliblar hali aniqlanmagan.")
        return
    await message.answer(await winners_text(db, db.contest_id))
