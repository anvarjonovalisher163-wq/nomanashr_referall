from aiogram import Router

from bot.handlers import user
from bot.handlers.admin import broadcast, channels, contest, panel, settings
from bot.handlers.admin import texts as admin_texts


def setup_routers() -> Router:
    root = Router(name="root")
    # Admin routerlari birinchi: FSM holatidagi admin xabarlari foydalanuvchi handlerlariga tushmasin.
    root.include_routers(
        panel.router,
        broadcast.router,
        channels.router,
        contest.router,
        settings.router,
        admin_texts.router,
        user.router,
    )
    return root
