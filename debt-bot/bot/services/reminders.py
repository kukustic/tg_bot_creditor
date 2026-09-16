"""
Логика напоминаний - обслуживает поток "время -> событие уведомления" из README
(планировщик опрашивает БД -> находит обязательства в "окне напоминания" ->
формирует список уведомлений на отправку).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from bot.models import NotificationLog, Obligation, ReminderRule, Status


def find_due_reminders(session: Session) -> list[Obligation]:
    """
    Возвращает обязательства, для которых сегодня нужно отправить напоминание.

    Правило: напоминаем, если
      - у обязательства есть включённое ReminderRule,
      - обязательство ещё не закрыто (CLOSED),
      - до due_date осталось <= days_before дней (и >= 0, либо уже просрочено -
        в этом случае тоже напоминаем, это важнее),
      - ещё не исчерпан лимит repeat_times,
      - сегодня уведомление по этому обязательству ещё не отправлялось.
    """
    today = dt.date.today()
    stmt = (
        select(Obligation)
        .join(ReminderRule, Obligation.id == ReminderRule.obligation_id)
        .where(
            ReminderRule.enabled.is_(True),
            Obligation.status != Status.CLOSED,
            ReminderRule.sent_count < ReminderRule.repeat_times,
        )
    )
    candidates = []
    for obligation in session.scalars(stmt):
        rule = obligation.reminder_rule
        days_left = (obligation.due_date.date() - today).days
        window_hit = days_left <= rule.days_before
        already_sent_today = any(
            log.sent_at.date() == today for log in _logs_for(session, obligation.id)
        )
        if window_hit and not already_sent_today:
            candidates.append(obligation)
    return candidates


def _logs_for(session: Session, obligation_id: int) -> list[NotificationLog]:
    stmt = select(NotificationLog).where(NotificationLog.obligation_id == obligation_id)
    return list(session.scalars(stmt).all())


def mark_reminder_sent(session: Session, obligation: Obligation) -> None:
    session.add(NotificationLog(obligation_id=obligation.id))
    obligation.reminder_rule.sent_count += 1
    session.commit()


def build_reminder_text(obligation: Obligation) -> str:
    from bot.services.obligations import remaining_amount
    from bot.models import ObligationRole

    days_left = (obligation.due_date.date() - dt.date.today()).days
    if obligation.role == ObligationRole.DEBT:
        side = f"Вы должны {obligation.counterparty_name}"
    else:
        side = f"{obligation.counterparty_name} должен(на) вам"

    if days_left > 0:
        when = f"через {days_left} дн. ({obligation.due_date.date():%d.%m.%Y})"
    elif days_left == 0:
        when = "сегодня!"
    else:
        when = f"просрочено на {-days_left} дн."

    remaining = remaining_amount(obligation)
    return (
        f"🔔 Напоминание об оплате\n\n"
        f"{side}\n"
        f"Остаток: {remaining:g}\n"
        f"Срок: {when}\n"
        f"Приоритет: {obligation.priority.value}"
    )
