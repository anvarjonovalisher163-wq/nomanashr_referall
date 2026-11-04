"""SQLite (aiosqlite) ustidagi ma'lumotlar qatlami."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    full_name   TEXT,
    username    TEXT,
    referrer_id INTEGER,
    is_blocked  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

-- Har bir foydalanuvchi faqat bir marta taklif qilingan bo'lishi mumkin.
CREATE TABLE IF NOT EXISTS referrals (
    referred_id  INTEGER PRIMARY KEY,
    referrer_id  INTEGER NOT NULL,
    contest_id   INTEGER NOT NULL,
    confirmed    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    confirmed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ref_referrer ON referrals (contest_id, referrer_id, confirmed);

CREATE TABLE IF NOT EXISTS winners (
    contest_id INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    place      INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (contest_id, user_id)
);

CREATE TABLE IF NOT EXISTS channels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    invite_link TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- E'lon ostidagi "alert" tugmalari matni (callback_data 64 baytdan oshmasligi uchun).
CREATE TABLE IF NOT EXISTS alerts (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL
);
"""

DEFAULT_SETTINGS: dict[str, str] = {
    "contest_id": "1",
    "contest_active": "0",
    "contest_drawn": "0",
    "required_refs": "5",
    "winners_count": "3",
    "draw_at": "",
    "bot_enabled": "1",
    "check_sub_on_draw": "1",
    "notify_new_users": "1",
    "log_chat_id": "",
    # 0 — do'st havola orqali botga kirishi bilan taklif sanaladi; 1 — kanallarga obuna bo'lgach
    "ref_requires_sub": "0",
    "announce_results": "1",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Channel:
    id: int
    chat_id: int
    title: str
    invite_link: str


@dataclass
class User:
    user_id: int
    full_name: str
    username: str | None
    referrer_id: int | None
    is_blocked: bool


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._settings: dict[str, str] = {}
        self._admins: set[int] = set()

    # ------------------------------------------------------------------ setup
    async def connect(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            await self._conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
            )
        await self._conn.commit()

        async with self._conn.execute("SELECT key, value FROM settings") as cur:
            self._settings = {row["key"]: row["value"] async for row in cur}
        async with self._conn.execute("SELECT user_id FROM admins") as cur:
            self._admins = {row["user_id"] async for row in cur}

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.connect() chaqirilmagan"
        return self._conn

    # --------------------------------------------------------------- settings
    def get(self, key: str) -> str:
        return self._settings.get(key, DEFAULT_SETTINGS.get(key, ""))

    def get_int(self, key: str) -> int:
        try:
            return int(self.get(key))
        except ValueError:
            return int(DEFAULT_SETTINGS.get(key, "0") or 0)

    def get_bool(self, key: str) -> bool:
        return self.get(key) == "1"

    async def set(self, key: str, value: str | int | bool) -> None:
        if isinstance(value, bool):
            value = "1" if value else "0"
        value = str(value)
        await self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.conn.commit()
        self._settings[key] = value

    async def delete_setting(self, key: str) -> None:
        await self.conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        await self.conn.commit()
        self._settings.pop(key, None)

    @property
    def contest_id(self) -> int:
        return self.get_int("contest_id")

    # ------------------------------------------------------------------ admins
    @property
    def db_admins(self) -> set[int]:
        return set(self._admins)

    async def add_admin(self, user_id: int) -> None:
        await self.conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        await self.conn.commit()
        self._admins.add(user_id)

    async def remove_admin(self, user_id: int) -> None:
        await self.conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
        await self.conn.commit()
        self._admins.discard(user_id)

    # ------------------------------------------------------------------- users
    async def get_user(self, user_id: int) -> User | None:
        async with self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return User(
            user_id=row["user_id"],
            full_name=row["full_name"] or "",
            username=row["username"],
            referrer_id=row["referrer_id"],
            is_blocked=bool(row["is_blocked"]),
        )

    async def add_user(
        self, user_id: int, full_name: str, username: str | None, referrer_id: int | None
    ) -> bool:
        """Yangi foydalanuvchini qo'shadi. Yangi bo'lsa True qaytaradi."""
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name, username, referrer_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, full_name, username, referrer_id, now_iso()),
        )
        created = cur.rowcount > 0
        if created and referrer_id:
            await self.conn.execute(
                "INSERT OR IGNORE INTO referrals (referred_id, referrer_id, contest_id, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, referrer_id, self.contest_id, now_iso()),
            )
        await self.conn.commit()
        return created

    async def update_user(self, user_id: int, full_name: str, username: str | None) -> None:
        await self.conn.execute(
            "UPDATE users SET full_name = ?, username = ?, is_blocked = 0 WHERE user_id = ?",
            (full_name, username, user_id),
        )
        await self.conn.commit()

    async def set_blocked(self, user_id: int, blocked: bool = True) -> None:
        await self.conn.execute(
            "UPDATE users SET is_blocked = ? WHERE user_id = ?", (int(blocked), user_id)
        )
        await self.conn.commit()

    async def all_user_ids(self, only_active: bool = True) -> list[int]:
        sql = "SELECT user_id FROM users"
        if only_active:
            sql += " WHERE is_blocked = 0"
        async with self.conn.execute(sql) as cur:
            return [row["user_id"] async for row in cur]

    async def export_users(self) -> list[aiosqlite.Row]:
        """Barcha foydalanuvchilar: kim taklif qilgan va joriy konkursdagi takliflar soni bilan."""
        async with self.conn.execute(
            "SELECT u.user_id, u.full_name, u.username, u.created_at, u.is_blocked, "
            "u.referrer_id, r.full_name AS referrer_name, r.username AS referrer_username, "
            "(SELECT COUNT(*) FROM referrals x WHERE x.referrer_id = u.user_id "
            " AND x.contest_id = ? AND x.confirmed = 1) AS refs "
            "FROM users u LEFT JOIN users r ON r.user_id = u.referrer_id ORDER BY u.created_at",
            (self.contest_id,),
        ) as cur:
            return await cur.fetchall()

    async def stats(self) -> dict[str, int]:
        async def scalar(sql: str, *args) -> int:
            async with self.conn.execute(sql, args) as cur:
                row = await cur.fetchone()
            return int(row[0] or 0)

        today = datetime.now(timezone.utc).date().isoformat()
        cid = self.contest_id
        return {
            "users": await scalar("SELECT COUNT(*) FROM users"),
            "active": await scalar("SELECT COUNT(*) FROM users WHERE is_blocked = 0"),
            "blocked": await scalar("SELECT COUNT(*) FROM users WHERE is_blocked = 1"),
            "today": await scalar("SELECT COUNT(*) FROM users WHERE created_at >= ?", today),
            "refs_total": await scalar(
                "SELECT COUNT(*) FROM referrals WHERE contest_id = ? AND confirmed = 1", cid
            ),
            "refs_pending": await scalar(
                "SELECT COUNT(*) FROM referrals WHERE contest_id = ? AND confirmed = 0", cid
            ),
            "pool": len(await self.pool(cid, self.get_int("required_refs"))),
        }

    # --------------------------------------------------------------- referrals
    async def confirm_referral(self, referred_id: int) -> int | None:
        """Taklifni tasdiqlaydi (obuna bo'lgandan keyin). Taklif qiluvchi ID sini qaytaradi."""
        async with self.conn.execute(
            "SELECT referrer_id FROM referrals WHERE referred_id = ? AND confirmed = 0",
            (referred_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        # Tasdiqlangan taklif joriy konkursga hisoblanadi.
        cur = await self.conn.execute(
            "UPDATE referrals SET confirmed = 1, confirmed_at = ?, contest_id = ? "
            "WHERE referred_id = ? AND confirmed = 0",
            (now_iso(), self.contest_id, referred_id),
        )
        await self.conn.commit()
        return row["referrer_id"] if cur.rowcount else None

    async def ref_count(self, user_id: int, contest_id: int | None = None) -> int:
        cid = contest_id or self.contest_id
        async with self.conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND contest_id = ? AND confirmed = 1",
            (user_id, cid),
        ) as cur:
            row = await cur.fetchone()
        return int(row[0])

    async def pool(self, contest_id: int, required: int) -> list[int]:
        """Random qozon: kamida `required` ta tasdiqlangan do'st taklif qilganlar."""
        async with self.conn.execute(
            "SELECT r.referrer_id FROM referrals r JOIN users u ON u.user_id = r.referrer_id "
            "WHERE r.contest_id = ? AND r.confirmed = 1 "
            "GROUP BY r.referrer_id HAVING COUNT(*) >= ? ORDER BY MIN(r.created_at)",
            (contest_id, max(required, 1)),
        ) as cur:
            return [row[0] async for row in cur]

    async def pool_details(self, contest_id: int, required: int) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT u.user_id, u.full_name, u.username, COUNT(*) AS cnt "
            "FROM referrals r JOIN users u ON u.user_id = r.referrer_id "
            "WHERE r.contest_id = ? AND r.confirmed = 1 "
            "GROUP BY r.referrer_id HAVING COUNT(*) >= ? ORDER BY cnt DESC",
            (contest_id, max(required, 1)),
        ) as cur:
            return await cur.fetchall()

    async def top(self, contest_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT u.user_id, u.full_name, u.username, COUNT(*) AS cnt "
            "FROM referrals r JOIN users u ON u.user_id = r.referrer_id "
            "WHERE r.contest_id = ? AND r.confirmed = 1 "
            "GROUP BY r.referrer_id ORDER BY cnt DESC, MIN(r.confirmed_at) LIMIT ?",
            (contest_id, limit),
        ) as cur:
            return await cur.fetchall()

    # ----------------------------------------------------------------- winners
    async def save_winners(self, contest_id: int, user_ids: list[int]) -> None:
        await self.conn.execute("DELETE FROM winners WHERE contest_id = ?", (contest_id,))
        await self.conn.executemany(
            "INSERT INTO winners (contest_id, user_id, place, created_at) VALUES (?, ?, ?, ?)",
            [(contest_id, uid, place, now_iso()) for place, uid in enumerate(user_ids, start=1)],
        )
        await self.conn.commit()

    async def winners(self, contest_id: int) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT w.place, w.user_id, u.full_name, u.username FROM winners w "
            "LEFT JOIN users u ON u.user_id = w.user_id WHERE w.contest_id = ? ORDER BY w.place",
            (contest_id,),
        ) as cur:
            return await cur.fetchall()

    # ---------------------------------------------------------------- channels
    async def channels(self) -> list[Channel]:
        async with self.conn.execute("SELECT * FROM channels ORDER BY id") as cur:
            return [
                Channel(row["id"], row["chat_id"], row["title"], row["invite_link"])
                async for row in cur
            ]

    async def add_channel(self, chat_id: int, title: str, invite_link: str) -> None:
        await self.conn.execute(
            "INSERT INTO channels (chat_id, title, invite_link) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title, "
            "invite_link = excluded.invite_link",
            (chat_id, title, invite_link),
        )
        await self.conn.commit()

    async def remove_channel(self, channel_id: int) -> None:
        await self.conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        await self.conn.commit()

    # ------------------------------------------------------------------ alerts
    async def add_alert(self, text: str) -> int:
        cur = await self.conn.execute("INSERT INTO alerts (text) VALUES (?)", (text,))
        await self.conn.commit()
        return int(cur.lastrowid)

    async def get_alert(self, alert_id: int) -> str | None:
        async with self.conn.execute("SELECT text FROM alerts WHERE id = ?", (alert_id,)) as cur:
            row = await cur.fetchone()
        return row["text"] if row else None
