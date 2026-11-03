"""Konkurs mantiqi: taklifni tasdiqlash, random qozon, g'oliblarni aniqlash va rejalashtiruvchi."""
from __future__ import annotations

import asyncio
import html
import logging
import random
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot import texts
from bot.config import Config
from bot.db import Database
from bot.keyboards import main_menu
from bot.services import subscription
from bot.services.broadcast import broadcast_text

log = logging.getLogger(__name__)

DATE_FORMAT = "%Y-%m-%d %H:%M"
_draw_lock = asyncio.Lock()


# ------------------------------------------------------------------ vaqt
def parse_date(text: str, config: Config) -> datetime | None:
    text = text.strip()
    for fmt in (DATE_FORMAT, "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=config.tz)
        except ValueError:
            continue
    return None


def draw_at(db: Database, config: Config) -> datetime | None:
    raw = db.get("draw_at")
    if not raw:
        return None
    try:
        return datetime.strptime(raw, DATE_FORMAT).replace(tzinfo=config.tz)
    except ValueError:
        return None


def draw_at_text(db: Database, config: Config) -> str:
    dt = draw_at(db, config)
    return dt.strftime("%d.%m.%Y %H:%M") if dt else html.escape(texts.get(db, "date_not_set"))


def user_mention(user_id: int, full_name: str | None, username: str | None = None) -> str:
    name = html.escape(full_name or str(user_id))
    suffix = f" (@{html.escape(username)})" if username else ""
    return f'<a href="tg://user?id={user_id}">{name}</a>{suffix}'


# ------------------------------------------------------------ takliflar
async def on_user_verified(bot: Bot, db: Database, user_id: int) -> None:
    """Foydalanuvchi barcha kanallarga obuna bo'lgach chaqiriladi: taklifni tasdiqlaydi."""
    referrer_id = await db.confirm_referral(user_id)
    if not referrer_id:
        return
    count = await db.ref_count(referrer_id)
    required = db.get_int("required_refs")
    contest_open = db.get_bool("contest_active") and not db.get_bool("contest_drawn")
    user = await db.get_user(user_id)
    name = html.escape(user.full_name) if user else str(user_id)

    text = texts.render(db, "ref_new", name=name, count=count, required=required)
    if contest_open and count == required:
        text += "\n\n" + texts.get(db, "ref_pool_joined")
    try:
        await bot.send_message(referrer_id, text)
    except TelegramAPIError:
        pass


# -------------------------------------------------------------- g'oliblar
async def run_draw(bot: Bot, db: Database, config: Config) -> list[int] | None:
    """G'oliblarni tasodifiy tanlaydi. Allaqachon o'tkazilgan bo'lsa None qaytaradi."""
    async with _draw_lock:
        if db.get_bool("contest_drawn"):
            return None

        contest_id = db.contest_id
        required = db.get_int("required_refs")
        winners_count = max(db.get_int("winners_count"), 1)
        candidates = await db.pool(contest_id, required)

        rng = random.SystemRandom()
        rng.shuffle(candidates)

        check_sub = db.get_bool("check_sub_on_draw")
        winners: list[int] = []
        for uid in candidates:
            if len(winners) >= winners_count:
                break
            if check_sub and await subscription.unsubscribed_channels(bot, db, uid, use_cache=False):
                log.info("Nomzod %s kanallardan chiqib ketgan — o'tkazib yuborildi", uid)
                continue
            winners.append(uid)

        await db.save_winners(contest_id, winners)
        await db.set("contest_drawn", True)
        await db.set("contest_active", False)

    log.info("Konkurs #%s yakunlandi. Qozonda: %s, g'oliblar: %s", contest_id, len(candidates), winners)
    await _announce(bot, db, config, contest_id, len(candidates), winners)
    return winners


async def winners_text(db: Database, contest_id: int) -> str:
    rows = await db.winners(contest_id)
    if not rows:
        return texts.get(db, "winners_none")
    lines = [
        texts.render(db, "winner_line", user=user_mention(r["user_id"], r["full_name"], r["username"]))
        for r in rows
    ]
    return texts.get(db, "winners_header") + "\n\n" + "\n".join(lines)


async def _announce(
    bot: Bot, db: Database, config: Config, contest_id: int, pool_size: int, winners: list[int]
) -> None:
    result_text = await winners_text(db, contest_id)
    result_text += "\n\n" + texts.render(db, "results_footer", pool=pool_size)

    # Konkurs yakunlandi — foydalanuvchilarga "G'oliblar" tugmasi bor yangi menyu yuboriladi
    admins = config.admin_ids | db.db_admins
    winner_dm = texts.render(db, "winner_dm", prize=texts.get(db, "prize_text"))
    for uid in winners:
        try:
            await bot.send_message(uid, winner_dm, reply_markup=main_menu(db, uid in admins))
        except TelegramAPIError:
            pass

    for admin_id in admins:
        try:
            await bot.send_message(
                admin_id, "🔔 <b>G'oliblar aniqlandi</b>\n\n" + result_text, reply_markup=main_menu(db, True)
            )
        except TelegramAPIError:
            pass

    if db.get_bool("announce_results"):
        await broadcast_text(
            bot, db, result_text, exclude=set(winners) | admins, reply_markup=main_menu(db, False)
        )


async def scheduler_loop(bot: Bot, db: Database, config: Config, interval: int = 20) -> None:
    """Belgilangan sanada g'oliblarni avtomatik aniqlaydi."""
    while True:
        try:
            when = draw_at(db, config)
            if (
                when
                and db.get_bool("contest_active")
                and not db.get_bool("contest_drawn")
                and datetime.now(config.tz) >= when
            ):
                await run_draw(bot, db, config)
        except Exception:  # noqa: BLE001 — rejalashtiruvchi to'xtab qolmasligi kerak
            log.exception("Rejalashtiruvchida xato")
        await asyncio.sleep(interval)
