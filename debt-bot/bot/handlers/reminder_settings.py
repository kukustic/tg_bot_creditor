from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.db import SessionLocal
from bot.services.obligations import get_obligation
from bot.states import ReminderSetup

router = Router(name="reminder_settings")


@router.callback_query(F.data.startswith("remind:") & (F.data.count(":") == 1))
async def open_reminder_settings(callback: CallbackQuery):
    oid = int(callback.data.split(":")[1])
    with SessionLocal() as session:
        obligation = get_obligation(session, oid)
        if obligation is None:
            await callback.answer("Запись не найдена.", show_alert=True)
            return
        rule = obligation.reminder_rule
        role = obligation.role.value
        text = (
            f"Настройка напоминаний для #{oid}\n\n"
            f"Статус: {'включены' if rule.enabled else 'выключены'}\n"
            f"За сколько дней начинать: {rule.days_before}\n"
            f"Сколько раз напомнить: {rule.repeat_times} (уже отправлено: {rule.sent_count})"
        )

    b = InlineKeyboardBuilder()
    b.button(text="🔛 Вкл/выкл", callback_data=f"remind:{oid}:toggle")
    b.button(text="⏱ За сколько дней", callback_data=f"remind:{oid}:days")
    b.button(text="🔁 Сколько раз", callback_data=f"remind:{oid}:times")
    b.button(text="⬅️ Назад", callback_data=f"open:{role}:{oid}")
    b.adjust(1)

    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("remind:") & F.data.endswith(":toggle"))
async def toggle_reminder(callback: CallbackQuery):
    oid = int(callback.data.split(":")[1])
    with SessionLocal() as session:
        obligation = get_obligation(session, oid)
        rule = obligation.reminder_rule
        rule.enabled = not rule.enabled
        if rule.enabled:
            # При повторном включении даём напоминаниям начаться заново,
            # иначе если лимит уже был исчерпан раньше, они не возобновятся.
            rule.sent_count = 0
        session.commit()
    await callback.answer("Обновлено")
    await open_reminder_settings(callback)


@router.callback_query(F.data.startswith("remind:") & F.data.endswith(":days"))
async def ask_days(callback: CallbackQuery, state: FSMContext):
    oid = int(callback.data.split(":")[1])
    await state.update_data(obligation_id=oid)
    await state.set_state(ReminderSetup.waiting_days_before)
    await callback.message.edit_text("За сколько дней до срока начинать напоминать? Введите число:")
    await callback.answer()


@router.message(ReminderSetup.waiting_days_before)
async def set_days(message: Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer("Нужно целое неотрицательное число. Попробуйте ещё раз:")
        return
    data = await state.get_data()
    with SessionLocal() as session:
        obligation = get_obligation(session, data["obligation_id"])
        obligation.reminder_rule.days_before = days
        obligation.reminder_rule.sent_count = 0  # сбрасываем прогресс, иначе окно откроется, а лимит уже исчерпан
        session.commit()
    await state.clear()
    await message.answer(f"Готово, буду начинать напоминать за {days} дн. до срока.")


@router.callback_query(F.data.startswith("remind:") & F.data.endswith(":times"))
async def ask_times(callback: CallbackQuery, state: FSMContext):
    oid = int(callback.data.split(":")[1])
    await state.update_data(obligation_id=oid)
    await state.set_state(ReminderSetup.waiting_repeat_times)
    await callback.message.edit_text("Сколько раз напомнить? Введите число:")
    await callback.answer()


@router.message(ReminderSetup.waiting_repeat_times)
async def set_times(message: Message, state: FSMContext):
    try:
        times = int(message.text.strip())
        if times < 1:
            raise ValueError
    except ValueError:
        await message.answer("Нужно целое число не меньше 1. Попробуйте ещё раз:")
        return
    data = await state.get_data()
    with SessionLocal() as session:
        obligation = get_obligation(session, data["obligation_id"])
        obligation.reminder_rule.repeat_times = times
        obligation.reminder_rule.sent_count = 0  # сбрасываем счётчик при изменении настроек
        session.commit()
    await state.clear()
    await message.answer(f"Готово, буду напоминать {times} дн.")