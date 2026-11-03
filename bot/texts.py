"""Foydalanuvchiga boradigan barcha matnlar va tugmalar.

Har bir matnni admin panel (📝 Matnlar) orqali o'zgartirish mumkin. O'zgartirilgan qiymat
`settings` jadvalida shu kalit bilan saqlanadi, aks holda standart qiymat ishlatiladi.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

from bot.db import Database

# Matn turlari:
#   html   — oddiy xabar (qalin, kursiv, havola saqlanadi)
#   plain  — formatlashsiz matn (masalan, ulashish matni)
#   button — tugma yozuvi (64 belgigacha)
#   alert  — tugma bosilganda chiqadigan oyna (200 belgigacha)
LIMITS = {"html": 3500, "plain": 1000, "button": 64, "alert": 200}


@dataclass(frozen=True)
class TextDef:
    key: str
    title: str
    default: str
    kind: str = "html"
    placeholders: tuple[str, ...] = ()
    rich: bool = False  # alohida xabar sifatida yuboriladi — media va tugma biriktirish mumkin


_DEFS: list[TextDef] = [
    # ------------------------------------------------------------ menyu tugmalari
    TextDef("btn_ref", "Tugma: taklif havolasi", "🔗 Taklif havolam", "button"),
    TextDef("btn_about", "Tugma: konkurs haqida", "ℹ️ Konkurs haqida", "button"),
    TextDef("btn_winners", "Tugma: g'oliblar", "🎁 G'oliblar", "button"),
    TextDef("btn_channel", "Tugma: kanalga obuna", "➕ {title}", "button", ("title",)),
    TextDef("btn_check_sub", "Tugma: obunani tekshirish", "✅ Tekshirish", "button"),
    TextDef("btn_share", "Tugma: do'stlarga ulashish", "📤 Do'stlarga ulashish", "button"),
    # ---------------------------------------------------------------- asosiy xabarlar
    TextDef(
        "welcome_text",
        "Start xabari",
        "👋 Assalomu alaykum, {name}!\n\n"
        "Do'stlaringizni taklif qiling va konkursda ishtirok eting. "
        "Belgilangan miqdordagi do'stni taklif qilganlar random qozonga qo'shiladi, "
        "g'oliblar esa belgilangan sanada tasodifiy tanlanadi. 🍀",
        placeholders=("name",), rich=True),
    TextDef("menu_hint", "Noma'lum xabarga javob", "👇 Quyidagi menyudan foydalaning.", rich=True),
    TextDef("bot_disabled", "Bot o'chirilganda", "🛠 Bot vaqtincha texnik ishlar sababli to'xtatilgan. Keyinroq urinib ko'ring.", rich=True),
    # ------------------------------------------------------------------- obuna
    TextDef(
        "sub_prompt",
        "Obuna bo'lish talabi",
        "❗️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling, so'ng «✅ Tekshirish» tugmasini bosing:", rich=True),
    TextDef("sub_alert_required", "Oyna: avval obuna bo'ling", "Avval kanallarga obuna bo'ling!", "alert"),
    TextDef("sub_alert_not_subscribed", "Oyna: obuna to'liq emas", "❌ Siz hali barcha kanallarga obuna bo'lmadingiz!", "alert"),
    TextDef("sub_alert_confirmed", "Oyna: obuna tasdiqlandi", "✅ Rahmat! Obuna tasdiqlandi.", "alert"),
    # ---------------------------------------------------------------- takliflar
    TextDef(
        "ref_link_text",
        "Taklif havolasi xabari",
        "🔗 <b>Sizning shaxsiy taklif havolangiz:</b>\n<code>{link}</code>\n\n"
        "Havolani do'stlaringizga yuboring. <b>{required}</b> ta do'stingiz shu havola orqali "
        "botga kirsa — siz random qozonga qo'shilasiz! 🎲\n\n{rule}",
        placeholders=("link", "required", "rule"), rich=True),
    TextDef("share_text", "Ulashish matni", "Konkursda ishtirok et va sovg'a yut! 🎁", "plain"),
    TextDef(
        "ref_new",
        "Yangi do'st qo'shilganda",
        "🎉 Sizning havolangiz orqali <b>{name}</b> botga qo'shildi!\n👥 Takliflaringiz: <b>{count}/{required}</b>",
        placeholders=("name", "count", "required"), rich=True),
    TextDef(
        "ref_pool_joined",
        "Qozonga qo'shilganda",
        "✅ Tabriklaymiz! Siz <b>random qozonga</b> qo'shildingiz. G'oliblar belgilangan sanada tasodifiy tanlanadi. 🍀",
    ),
    # ------------------------------------------------------------- konkurs haqida
    TextDef(
        "about_text",
        "Konkurs haqida",
        "ℹ️ <b>Konkurs haqida</b>\n\n"
        "Holat: {status}\n"
        "👥 Qozonga kirish sharti: <b>{required}</b> ta do'st taklif qilish\n"
        "🏆 G'oliblar soni: <b>{winners}</b> ta\n"
        "📅 G'oliblar aniqlanadigan sana: <b>{date}</b>\n\n"
        "{prize}\n\n"
        "{rule}",
        placeholders=("status", "required", "winners", "date", "prize", "rule"), rich=True),
    TextDef(
        "rule_no_sub",
        "Shart: faqat havola orqali kirish",
        "❗️ Do'stingiz botga havolangiz orqali birinchi marta kirgan bo'lishi kerak.",
    ),
    TextDef(
        "rule_with_sub",
        "Shart: kirish + kanallarga obuna",
        "❗️ Do'stingiz botga havolangiz orqali birinchi marta kirgan va barcha majburiy kanallarga "
        "obuna bo'lgan bo'lishi kerak.",
    ),
    TextDef("state_active", "Konkurs holati: faol", "🟢 Faol"),
    TextDef("state_inactive", "Konkurs holati: faol emas", "⏸ Faol emas"),
    TextDef("state_drawn", "Konkurs holati: yakunlangan", "🏁 Yakunlangan"),
    TextDef("date_not_set", "Sana belgilanmagan", "belgilanmagan", "plain"),
    TextDef("prize_text", "Sovg'alar matni", "🎁 Sovg'alar haqida ma'lumot tez orada e'lon qilinadi."),
    # ---------------------------------------------------------------- g'oliblar
    TextDef("winners_not_yet", "G'oliblar hali aniqlanmagan", "⏳ G'oliblar hali aniqlanmagan.", rich=True),
    TextDef("winners_header", "G'oliblar sarlavhasi", "🏆 <b>Konkurs g'oliblari:</b>", rich=True),
    TextDef("winner_line", "G'olib qatori", "🎉 {user}", placeholders=("user",)),
    TextDef(
        "winners_none", "G'olib yo'q",
        "😔 Qozonda ishtirokchilar bo'lmagani sababli g'oliblar aniqlanmadi.",
    ),
    TextDef(
        "results_footer", "Natija oxiri",
        "🎲 Random qozondagi ishtirokchilar: <b>{pool}</b> ta", placeholders=("pool",),
    ),
    TextDef(
        "winner_dm",
        "G'olibga xabar",
        "🎉 <b>Tabriklaymiz!</b> Siz konkurs g'oliblaridan biri bo'ldingiz!\n\n{prize}\n\n"
        "Tez orada admin siz bilan bog'lanadi.",
        placeholders=("prize",), rich=True),
]

TEXTS: dict[str, TextDef] = {d.key: d for d in _DEFS}
ORDER: list[str] = [d.key for d in _DEFS]
MENU_BUTTONS = ("btn_ref", "btn_about", "btn_winners")


def get(db: Database, key: str) -> str:
    value = db.get(key)
    return value if value else TEXTS[key].default


def render(db: Database, key: str, **values: object) -> str:
    """Matnni oladi va {placeholder} larni almashtiradi.

    Foydalanuvchi kiritgan qiymatlar (ism va h.k.) chaqiruvchi tomonidan html.escape qilinishi kerak.
    """
    text = get(db, key)
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def is_custom(db: Database, key: str) -> bool:
    value = db.get(key)
    return (bool(value) and value != TEXTS[key].default) or bool(
        db.get(f"{key}__media") or db.get(f"{key}__buttons")
    )


def strip_html(text: str) -> str:
    """HTML teglarni olib tashlaydi (alert oynalari uchun)."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def ref_rule(db: Database) -> str:
    """Taklif qachon sanalishi haqidagi shart (sozlamaga qarab)."""
    return get(db, "rule_with_sub" if db.get_bool("ref_requires_sub") else "rule_no_sub")
