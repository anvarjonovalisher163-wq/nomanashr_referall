"""Ishga tushirish: python -m bot"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.config import load_config
from bot.db import Database
from bot.handlers import setup_routers
from bot.middlewares import AccessMiddleware
from bot.services import rich
from bot.services.contest import scheduler_loop
from bot.services.notifier import notifier_loop


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = load_config()
    db = Database(config.db_path)
    await db.connect()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    rich.BOT_USERNAME = me.username or ""

    dp = Dispatcher(storage=MemoryStorage())
    dp["config"] = config
    dp["db"] = db
    dp["bot_username"] = me.username

    access = AccessMiddleware()
    dp.message.outer_middleware(access)
    dp.callback_query.outer_middleware(access)
    dp.include_router(setup_routers())

    await bot.set_my_commands([BotCommand(command="start", description="Botni ishga tushirish")])

    scheduler = asyncio.create_task(scheduler_loop(bot, db, config))
    notifier = asyncio.create_task(notifier_loop(bot, db, config))
    logging.info("Bot ishga tushdi: @%s", me.username)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.cancel()
        notifier.cancel()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
