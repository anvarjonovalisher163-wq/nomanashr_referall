from aiogram import Router

from bot.handlers import user
from bot.handlers.admin import broadcast, channels, contest, panel, settings


def setup_routers() -> Router:
    root = Router(name="root")
    # Admin routerlari birinchi: FSM holatidagi admin xabarlari foydalanuvchi handlerlariga tushmasin.
    root.include_routers(
        panel.router,
        broadcast.router,
        channels.router,
        contest.router,
        settings.router,
        user.router,
    )
    return root
