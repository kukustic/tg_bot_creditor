"""
Планировщик — реализует поток "время -> уведомление" из README.
Периодически (интервал задаётся в .env) опрашивает БД, находит обязательства,
для которых наступило "окно напоминания", и рассылает сообщения через Telegram.
"""
import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.db import SessionLocal
from bot.services.reminders import build_reminder_text, find_due_reminders, mark_reminder_sent

logger = logging.getLogger(__name__)


async def check_and_send_reminders(bot: Bot) -> None:
    with SessionLocal() as session:
        due = find_due_reminders(session)
        for obligation in due:
            text = build_reminder_text(obligation)
            try:
                await bot.send_message(chat_id=obligation.user_id, text=text)
                mark_reminder_sent(session, obligation)
            except Exception:
                logger.exception("Не удалось отправить напоминание по обязательству #%s", obligation.id)


def setup_scheduler(bot: Bot, interval_minutes: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_send_reminders,
        "interval",
        minutes=interval_minutes,
        args=[bot],
        id="reminder_check",
        replace_existing=True,
    )
    return scheduler
