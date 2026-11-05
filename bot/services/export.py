"""Foydalanuvchilar ro'yxatini CSV (Excel / Google Sheets) faylga chiqarish va avtomatik yuborish."""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import BufferedInputFile

from bot.config import Config
from bot.db import Database

log = logging.getLogger(__name__)

# Admin tanlashi mumkin bo'lgan oraliqlar (daqiqa); 0 — o'chiq
INTERVAL_CHOICES = (0, 15, 30, 60, 120, 180, 360, 720, 1440)


def interval_label(minutes: int) -> str:
    if minutes <= 0:
        return "o'chiq"
    if minutes < 60:
        return f"har {minutes} daqiqada"
    if minutes % 60 == 0:
        return f"har {minutes // 60} soatda" if minutes != 1440 else "kuniga 1 marta"
    return f"har {minutes} daqiqada"


def _local(value: str | None, config: Config) -> str:
    try:
        return datetime.fromisoformat(value).astimezone(config.tz).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return value or ""


async def build_users_file(db: Database, config: Config) -> tuple[BufferedInputFile, int]:
    rows = await db.export_users()
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")  # ";" — Excel'da ustunlar to'g'ri ajraladi
    writer.writerow([
        "ID", "Ism", "Username", "Qo'shilgan vaqt", "Taklif qilgan (ID)", "Taklif qilgan (ism)",
        "Taklif qilgan (username)", "Takliflari soni", "Botni bloklagan", "Oxirgi faollik",
    ])
    for r in rows:
        writer.writerow([
            r["user_id"], r["full_name"] or "", f"@{r['username']}" if r["username"] else "",
            _local(r["created_at"], config),
            r["referrer_id"] or "", r["referrer_name"] or "",
            f"@{r['referrer_username']}" if r["referrer_username"] else "",
            r["refs"], "ha" if r["is_blocked"] else "yo'q", _local(r["last_seen"], config),
        ])
    data = buffer.getvalue().encode("utf-8-sig")
    name = f"foydalanuvchilar_{datetime.now(config.tz):%Y-%m-%d_%H-%M}.csv"
    return BufferedInputFile(data, filename=name), len(rows)


def targets(db: Database, config: Config) -> list[int]:
    raw = db.get("log_chat_id")
    if raw and raw.lstrip("-").isdigit():
        return [int(raw)]
    return sorted(config.admin_ids)


async def export_loop(bot: Bot, db: Database, config: Config) -> None:
    """Sozlamadagi oraliqda foydalanuvchilar faylini log kanalga (yoki adminlarga) yuboradi."""
    while True:
        await asyncio.sleep(60)
        try:
            minutes = db.get_int("export_interval")
            if minutes <= 0:
                continue
            last_raw = db.get("export_last_at")
            now = datetime.now(config.tz)
            if last_raw:
                try:
                    if now - datetime.fromisoformat(last_raw) < timedelta(minutes=minutes):
                        continue
                except ValueError:
                    pass
            await db.set("export_last_at", now.isoformat(timespec="seconds"))
            file, total = await build_users_file(db, config)
            caption = f"📥 Avtomatik eksport ({interval_label(minutes)})\n👥 Jami: {total} ta foydalanuvchi"
            for chat_id in targets(db, config):
                try:
                    await bot.send_document(chat_id, file, caption=caption)
                except TelegramRetryAfter as exc:
                    await asyncio.sleep(exc.retry_after)
                except TelegramAPIError as exc:
                    log.warning("Avtomatik eksport yuborilmadi (%s): %s", chat_id, exc)
        except Exception:  # noqa: BLE001 — sikl to'xtab qolmasligi kerak
            log.exception("Avtomatik eksportda xato")
