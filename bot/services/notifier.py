"""Yangi foydalanuvchilar haqida adminlarga yoki log kanalga xabar berish.

Yangi foydalanuvchilar to'g'ridan-to'g'ri bazadan olinadi: qaysi foydalanuvchigacha xabar berilgani
`settings.notify_cursor` da saqlanadi. Shuning uchun bot qayta ishga tushsa yoki Telegram xato qaytarsa ham
hech kim tushib qolmaydi — xabar keyingi urinishda yuboriladi.

Telegram bitta chatga daqiqasiga ~20 tadan ko'p xabar yuborishga ruxsat bermaydi, shuning uchun yangi
foydalanuvchilar har 10 soniyada bitta umumiy xabar bo'lib (25 tagacha) yuboriladi.
"""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from bot.config import Config
from bot.db import Database

log = logging.getLogger(__name__)

INTERVAL = 10  # soniya
MAX_PER_MESSAGE = 25


def _mention(user_id: int, name: str | None, username: str | None) -> str:
    text = f'<a href="tg://user?id={user_id}">{html.escape(name or str(user_id))}</a>'
    if username:
        text += f" @{html.escape(username)}"
    return text


def _targets(db: Database, config: Config) -> list[int]:
    raw = db.get("log_chat_id")
    if raw and raw.lstrip("-").isdigit():
        return [int(raw)]
    return sorted(config.admin_ids)


async def _init_cursor(db: Database) -> None:
    """Birinchi ishga tushishda eski foydalanuvchilar haqida xabar yubormaslik uchun kursorni oxiriga qo'yadi."""
    if db.get("notify_cursor"):
        return
    async with db.conn.execute("SELECT created_at, user_id FROM users ORDER BY created_at DESC, user_id DESC LIMIT 1") as cur:
        row = await cur.fetchone()
    await db.set("notify_cursor", f"{row[0]}|{row[1]}" if row else "|0")


async def _next_batch(db: Database) -> tuple[list, int]:
    created, _, uid = db.get("notify_cursor").partition("|")
    uid = int(uid or 0)
    async with db.conn.execute(
        "SELECT u.user_id, u.full_name, u.username, u.created_at, u.referrer_id, "
        "r.full_name AS ref_name, r.username AS ref_username "
        "FROM users u LEFT JOIN users r ON r.user_id = u.referrer_id "
        "WHERE (u.created_at > ?) OR (u.created_at = ? AND u.user_id > ?) "
        "ORDER BY u.created_at, u.user_id LIMIT ?",
        (created, created, uid, MAX_PER_MESSAGE),
    ) as cur:
        rows = await cur.fetchall()
    # Partiyadagi birinchi foydalanuvchining tartib raqami
    async with db.conn.execute(
        "SELECT COUNT(*) FROM users WHERE (created_at < ?) OR (created_at = ? AND user_id <= ?)",
        (created, created, uid),
    ) as cur:
        before = (await cur.fetchone())[0]
    return rows, before + 1


def _render(rows, first_number: int, total: int, config: Config) -> str:
    lines = []
    for number, r in enumerate(rows, start=first_number):
        line = f"<b>#{number}</b> 👤 {_mention(r['user_id'], r['full_name'], r['username'])} — <code>{r['user_id']}</code>"
        if r["referrer_id"]:
            line += f"\n      ↳ taklif qildi: {_mention(r['referrer_id'], r['ref_name'], r['ref_username'])}"
        try:
            joined = datetime.fromisoformat(r["created_at"]).astimezone(config.tz)
            line += f"\n      🕒 {joined:%d.%m.%Y %H:%M}"
        except (TypeError, ValueError):
            pass
        lines.append(line)
    return f"🆕 <b>Yangi foydalanuvchilar: {len(rows)}</b> (jami: {total})\n\n" + "\n".join(lines)


async def notifier_loop(bot: Bot, db: Database, config: Config) -> None:
    await _init_cursor(db)
    while True:
        await asyncio.sleep(INTERVAL)
        try:
            if not db.get_bool("notify_new_users"):
                # O'chiq paytda qo'shilganlar keyin yoqilganda yopirilib kelmasligi uchun kursorni suramiz
                await db.set("notify_cursor", "")
                await _init_cursor(db)
                continue
            rows, first_number = await _next_batch(db)
            if not rows:
                continue
            total = (await db.stats())["users"]
            text = _render(rows, first_number, total, config)
            delivered = False
            for chat_id in _targets(db, config):
                try:
                    await bot.send_message(chat_id, text, disable_web_page_preview=True)
                    delivered = True
                except TelegramRetryAfter as exc:
                    await asyncio.sleep(exc.retry_after)
                except TelegramAPIError as exc:
                    log.warning("Yangi foydalanuvchilar xabari yuborilmadi (%s): %s", chat_id, exc)
            if delivered:
                last = rows[-1]
                await db.set("notify_cursor", f"{last['created_at']}|{last['user_id']}")
        except Exception:  # noqa: BLE001 — sikl to'xtab qolmasligi kerak
            log.exception("Yangi foydalanuvchilar xabarnomasida xato")
