from aiogram.fsm.state import State, StatesGroup


class AddObligation(StatesGroup):
    """Пошаговый сценарий добавления долга/займа (UC2 из README)."""
    waiting_counterparty = State()
    waiting_amount = State()
    waiting_interest = State()
    waiting_due_date = State()
    waiting_priority = State()
    waiting_note = State()


class AddPayment(StatesGroup):
    """Сценарий внесения платежа (UC4)."""
    waiting_amount = State()


class ReminderSetup(StatesGroup):
    """Сценарий настройки напоминаний под конкретное обязательство (UC5)."""
    waiting_days_before = State()
    waiting_repeat_times = State()
