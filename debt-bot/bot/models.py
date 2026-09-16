"""
ORM-модели — формализация сущностей информационной модели (см. README, раздел
«Сущности»). Каждая таблица здесь — это одна сущность из ER-схемы.

Ключевое архитектурное решение: сущность Obligation (Обязательство) —
ОБЩАЯ и для долгов, и для займов. Роль (`role`) отличает, кто кому должен.
Это сознательное упрощение: с точки зрения структуры данных долг и заём —
зеркальные записи одной и той же сущности, различающиеся только точкой
зрения пользователя. Дублировать таблицы (Debt / Loan) было бы избыточно
и создавало бы риск рассинхронизации бизнес-логики.
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db import Base


class ObligationRole(str, enum.Enum):
    """Роль обязательства с точки зрения пользователя бота."""
    DEBT = "debt"   # я должен (пользователь выступает должником)
    LOAN = "loan"   # мне должны (пользователь выступает кредитором)


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Status(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    OVERDUE = "overdue"


class User(Base):
    """Пользователь бота. Одна и та же персона может вести и долги, и займы."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram user_id
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    obligations: Mapped[list["Obligation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Obligation(Base):
    """
    Обязательство — центральная сущность модели.
    role=DEBT  -> "я должен" (counterparty = кредитор)
    role=LOAN  -> "мне должны" (counterparty = должник)
    """
    __tablename__ = "obligations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    role: Mapped[ObligationRole] = mapped_column(Enum(ObligationRole))

    counterparty_name: Mapped[str] = mapped_column(String(128))
    amount: Mapped[float] = mapped_column(Float)  # исходная сумма
    interest_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # % годовых, опционально
    due_date: Mapped[dt.datetime] = mapped_column(DateTime)  # хранится datetime, для сравнений используем .date()
    priority: Mapped[Priority] = mapped_column(Enum(Priority), default=Priority.MEDIUM)
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.ACTIVE)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="obligations")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="obligation", cascade="all, delete-orphan"
    )
    reminder_rule: Mapped["ReminderRule"] = relationship(
        back_populates="obligation", cascade="all, delete-orphan", uselist=False
    )


class Payment(Base):
    """Факт (частичной или полной) оплаты по конкретному обязательству."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    obligation_id: Mapped[int] = mapped_column(ForeignKey("obligations.id"))
    amount: Mapped[float] = mapped_column(Float)
    paid_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    obligation: Mapped["Obligation"] = relationship(back_populates="payments")


class ReminderRule(Base):
    """
    Настройка напоминаний для конкретного обязательства.
    enabled       — слать ли вообще напоминания
    days_before   — за сколько дней до due_date начинать напоминать
    repeat_times  — сколько раз всего напомнить (равномерно от days_before до due_date)
    sent_count    — сколько напоминаний уже отправлено (для контроля повторов)
    """
    __tablename__ = "reminder_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    obligation_id: Mapped[int] = mapped_column(ForeignKey("obligations.id"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    days_before: Mapped[int] = mapped_column(Integer, default=3)
    repeat_times: Mapped[int] = mapped_column(Integer, default=1)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)

    obligation: Mapped["Obligation"] = relationship(back_populates="reminder_rule")


class NotificationLog(Base):
    """Журнал фактически отправленных уведомлений — защита от повторной отправки в тот же день."""
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    obligation_id: Mapped[int] = mapped_column(ForeignKey("obligations.id"))
    sent_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
