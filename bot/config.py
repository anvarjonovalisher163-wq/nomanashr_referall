"""Muhit o'zgaruvchilaridan (.env) konfiguratsiyani o'qish."""
from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: frozenset[int]
    db_path: str
    tz: ZoneInfo


def load_config() -> Config:
    load_dotenv()

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN topilmadi. .env faylini to'ldiring (.env.example ga qarang).")

    raw_admins = os.getenv("ADMIN_IDS", "")
    admin_ids = frozenset(
        int(part) for part in raw_admins.replace(" ", "").split(",") if part.lstrip("-").isdigit()
    )
    if not admin_ids:
        raise RuntimeError("ADMIN_IDS bo'sh. Kamida bitta admin Telegram ID sini kiriting.")

    return Config(
        bot_token=token,
        admin_ids=admin_ids,
        db_path=os.getenv("DB_PATH", "data/bot.db"),
        tz=ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent")),
    )
