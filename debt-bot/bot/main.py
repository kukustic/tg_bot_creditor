import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from bot.db import init_db
from bot.handlers import common, obligations, reminder_settings
from bot.scheduler import setup_scheduler

# debtor.py / creditor.py — тонкие точки входа веток бизнес-логики, каждая
# реэкспортирует один и тот же router из obligations.py (см. пояснение там).
# Подключать их отдельно не нужно и нельзя — это тот же объект Router,
# aiogram не допускает повторного включения одного router в диспетчер.

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не задан. Скопируйте .env.example в .env и впишите токен.")

    interval = int(os.getenv("REMINDER_CHECK_INTERVAL_MINUTES", "60"))

    init_db()

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Порядок подключения важен только для читаемости — обработчики
    # не пересекаются по своим фильтрам.
    dp.include_router(common.router)
    dp.include_router(obligations.router)  # используется debtor.py/creditor.py под капотом
    dp.include_router(reminder_settings.router)

    scheduler = setup_scheduler(bot, interval)
    scheduler.start()
    logger.info("Планировщик напоминаний запущен, интервал: %s мин.", interval)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
