from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.models import Priority


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🧾 Я должен (мои долги)", callback_data="menu:role:debt")
    b.button(text="💰 Мне должны (мои займы)", callback_data="menu:role:loan")
    b.button(text="📊 Общая сводка", callback_data="menu:summary")
    b.adjust(1)
    return b.as_markup()


def role_menu_kb(role: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить запись", callback_data=f"role:{role}:add")
    b.button(text="📋 Список", callback_data=f"role:{role}:list")
    b.button(text="⬅️ В главное меню", callback_data="menu:root")
    b.adjust(1)
    return b.as_markup()


def priority_kb(role: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔴 Высокий", callback_data=f"add:{role}:priority:{Priority.HIGH.value}")
    b.button(text="🟡 Средний", callback_data=f"add:{role}:priority:{Priority.MEDIUM.value}")
    b.button(text="🟢 Низкий", callback_data=f"add:{role}:priority:{Priority.LOW.value}")
    b.adjust(1)
    return b.as_markup()


def skip_kb(step: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Пропустить", callback_data=f"skip:{step}")
    return b.as_markup()


def yes_no_kb(prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Да", callback_data=f"{prefix}:yes")
    b.button(text="Нет", callback_data=f"{prefix}:no")
    b.adjust(2)
    return b.as_markup()


def obligation_item_kb(obligation_id: int, role: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💵 Внести платёж", callback_data=f"pay:{obligation_id}")
    b.button(text="🔔 Напоминания", callback_data=f"remind:{obligation_id}")
    b.button(text="❌ Удалить", callback_data=f"del:{obligation_id}")
    b.button(text="⬅️ К списку", callback_data=f"role:{role}:list")
    b.adjust(1)
    return b.as_markup()


def back_to_list_kb(role: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ К списку", callback_data=f"role:{role}:list")
    return b.as_markup()
