"""
Бизнес-логика по обязательствам: создание, платежи, пересчёт остатка/статуса,
простая финансовая аналитика (проценты, сводка).

Это и есть формализация потока «изменение статуса» из README:
платёж -> пересчёт остатка -> пересчёт статуса -> (опц.) пересчёт процентов.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from bot.models import (
    NotificationLog,
    Obligation,
    ObligationRole,
    Payment,
    Priority,
    ReminderRule,
    Status,
    User,
)


def get_or_create_user(session: Session, tg_id: int, username: str | None, full_name: str | None) -> User:
    user = session.get(User, tg_id)
    if user is None:
        user = User(id=tg_id, username=username, full_name=full_name)
        session.add(user)
        session.commit()
    return user


def create_obligation(
    session: Session,
    user_id: int,
    role: ObligationRole,
    counterparty_name: str,
    amount: float,
    due_date: dt.date,
    priority: Priority = Priority.MEDIUM,
    interest_rate: float | None = None,
    note: str | None = None,
) -> Obligation:
    if amount <= 0:
        raise ValueError("Сумма обязательства должна быть положительной.")
    if interest_rate is not None and interest_rate < 0:
        raise ValueError("Процентная ставка не может быть отрицательной.")
    if due_date.date() < dt.date.today():
        raise ValueError("Дата платежа не может быть в прошлом.")

    obligation = Obligation(
        user_id=user_id,
        role=role,
        counterparty_name=counterparty_name,
        amount=amount,
        due_date=due_date,
        priority=priority,
        interest_rate=interest_rate,
        note=note,
        status=Status.ACTIVE,
    )
    session.add(obligation)
    session.commit()
    session.refresh(obligation)

    # Дефолтное правило напоминаний создаётся сразу, чтобы пользователю не
    # приходилось отдельно "включать" уведомления - он может позже их
    # выключить или перенастроить (UC5).
    rule = ReminderRule(obligation_id=obligation.id, enabled=True, days_before=3, repeat_times=1)
    session.add(rule)
    session.commit()

    return obligation


def list_obligations(session: Session, user_id: int, role: ObligationRole) -> list[Obligation]:
    stmt = (
        select(Obligation)
        .where(Obligation.user_id == user_id, Obligation.role == role)
        .order_by(Obligation.status, Obligation.due_date)
    )
    return list(session.scalars(stmt).all())


def get_obligation(session: Session, obligation_id: int) -> Obligation | None:
    return session.get(Obligation, obligation_id)


def paid_amount(obligation: Obligation) -> float:
    return sum(p.amount for p in obligation.payments)


def remaining_amount(obligation: Obligation) -> float:
    return round(obligation.amount - paid_amount(obligation), 2)


def add_payment(session: Session, obligation: Obligation, amount: float) -> Payment:
    if amount <= 0:
        raise ValueError("Сумма платежа должна быть положительной.")
    remaining = remaining_amount(obligation)
    # Небольшой допуск на погрешность float, чтобы не блокировать платёж "в ноль"
    if amount - remaining > 0.01:
        raise ValueError(f"Сумма платежа превышает остаток по обязательству ({remaining:g}).")

    payment = Payment(obligation_id=obligation.id, amount=amount)
    session.add(payment)
    session.commit()

    # Пересчёт статуса после платежа
    if remaining_amount(obligation) <= 0:
        obligation.status = Status.CLOSED
    elif obligation.due_date.date() < dt.date.today():
        obligation.status = Status.OVERDUE
    else:
        obligation.status = Status.ACTIVE
    session.commit()
    session.refresh(obligation)
    return payment


def refresh_overdue_statuses(session: Session, user_id: int) -> None:
    """Помечает просроченные, но ещё не закрытые обязательства статусом OVERDUE."""
    stmt = select(Obligation).where(
        Obligation.user_id == user_id,
        Obligation.status == Status.ACTIVE,
    )
    today = dt.date.today()
    for obligation in session.scalars(stmt):
        if obligation.due_date.date() < today:
            obligation.status = Status.OVERDUE
    session.commit()


def delete_obligation(session: Session, obligation: Obligation) -> None:
    session.delete(obligation)
    session.commit()


def estimate_accrued_interest(obligation: Obligation) -> float:
    """
    Упрощённая финансовая аналитика (опциональная часть задания):
    простые проценты на остаток долга, накопленные со дня создания записи
    до сегодняшнего дня, из расчёта interest_rate % годовых.
    Это оценка "сколько набежало", а не юридически точный расчёт.
    """
    if not obligation.interest_rate:
        return 0.0
    days = (dt.date.today() - obligation.created_at.date()).days
    if days <= 0:
        return 0.0
    principal = remaining_amount(obligation)
    rate_per_day = obligation.interest_rate / 100 / 365
    return round(principal * rate_per_day * days, 2)


def summary_for_user(session: Session, user_id: int) -> dict:
    """Сводка для команды 'Общая сводка': сколько всего должен и сколько должны ему."""
    refresh_overdue_statuses(session, user_id)

    debts = list_obligations(session, user_id, ObligationRole.DEBT)
    loans = list_obligations(session, user_id, ObligationRole.LOAN)

    def totals(items: list[Obligation]) -> dict:
        active = [o for o in items if o.status != Status.CLOSED]
        remaining = sum(remaining_amount(o) for o in active)
        interest = sum(estimate_accrued_interest(o) for o in active)
        overdue_count = sum(1 for o in active if o.status == Status.OVERDUE)
        return {
            "count_active": len(active),
            "remaining": round(remaining, 2),
            "accrued_interest": round(interest, 2),
            "overdue_count": overdue_count,
        }

    return {"debts": totals(debts), "loans": totals(loans)}