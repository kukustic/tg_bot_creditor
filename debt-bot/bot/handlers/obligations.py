"""
Общий обработчик для обеих веток (должник/кредитор).

Почему один файл, а не debtor.py + creditor.py с дублированным кодом:
как зафиксировано в README (сущность Obligation), долг и заём отличаются
только значением поля role, вся остальная логика (добавление, список,
платежи, напоминания) идентична. Ветвление по роли происходит через
параметр в callback_data ("role:debt:..." / "role:loan:..."), а не через
дублирование обработчиков. Тонкие файлы handlers/debtor.py и
handlers/creditor.py оставлены как явные точки входа веток и просто
подключают этот router.
"""
from __future__ import annotations

import datetime as dt

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.db import SessionLocal
from bot.keyboards import (
    back_to_list_kb,
    obligation_item_kb,
    priority_kb,
    role_menu_kb,
    skip_kb,
)
from bot.models import ObligationRole, Priority
from bot.services.obligations import (
    add_payment,
    create_obligation,
    delete_obligation,
    estimate_accrued_interest,
    get_obligation,
    list_obligations,
    remaining_amount,
)
from bot.states import AddObligation, AddPayment

router = Router(name="obligations")

ROLE_LABELS = {
    "debt": {
        "counterparty_prompt": "Кому вы должны? Введите имя кредитора.",
        "noun": "долг",
        "noun_plural": "долги",
    },
    "loan": {
        "counterparty_prompt": "Кому вы одолжили? Введите имя должника.",
        "noun": "заём",
        "noun_plural": "займы",
    },
}


def _role_enum(role: str) -> ObligationRole:
    return ObligationRole.DEBT if role == "debt" else ObligationRole.LOAN


# ---------- UC2: добавление обязательства (пошаговый FSM) ----------

@router.callback_query(F.data.startswith("role:") & F.data.contains(":add"))
async def start_add(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split(":")[1]
    await state.update_data(role=role)
    await state.set_state(AddObligation.waiting_counterparty)
    await callback.message.edit_text(ROLE_LABELS[role]["counterparty_prompt"])
    await callback.answer()


@router.message(AddObligation.waiting_counterparty)
async def add_counterparty(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Имя не может быть пустым. Введите имя ещё раз:")
        return
    await state.update_data(counterparty_name=name)
    await state.set_state(AddObligation.waiting_amount)
    await message.answer("Введите сумму (число, например 15000 или 15000.50):")


@router.message(AddObligation.waiting_amount)
async def add_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Похоже, это не похоже на положительное число. Попробуйте ещё раз:")
        return
    await state.update_data(amount=amount)
    await state.set_state(AddObligation.waiting_interest)
    await message.answer(
        "Есть ли процентная ставка (% годовых)? Введите число или нажмите «Пропустить».",
        reply_markup=skip_kb("interest"),
    )


@router.message(AddObligation.waiting_interest)
async def add_interest(message: Message, state: FSMContext):
    try:
        interest = float(message.text.replace(",", ".").replace("%", "").strip())
    except ValueError:
        await message.answer("Нужно число (например 12) или нажмите «Пропустить».")
        return
    if interest < 0:
        await message.answer("Ставка не может быть отрицательной. Введите 0 или положительное число, либо «Пропустить».")
        return
    await state.update_data(interest_rate=interest)
    await _ask_due_date(message, state)


@router.callback_query(AddObligation.waiting_interest, F.data == "skip:interest")
async def skip_interest(callback: CallbackQuery, state: FSMContext):
    await state.update_data(interest_rate=None)
    await callback.answer()
    await _ask_due_date(callback.message, state)


async def _ask_due_date(message: Message, state: FSMContext):
    await state.set_state(AddObligation.waiting_due_date)
    await message.answer("Введите дату платежа в формате ДД.ММ.ГГГГ (например 25.12.2026):")


@router.message(AddObligation.waiting_due_date)
async def add_due_date(message: Message, state: FSMContext):
    try:
        due_date = dt.datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except ValueError:
        await message.answer("Не получилось распознать дату. Формат: ДД.ММ.ГГГГ. Попробуйте ещё раз:")
        return
    if due_date.date() < dt.date.today():
        await message.answer(
            "Дата платежа не может быть в прошлом. Введите сегодняшнюю или будущую дату (ДД.ММ.ГГГГ):"
        )
        return
    await state.update_data(due_date=due_date.isoformat())
    data = await state.get_data()
    await state.set_state(AddObligation.waiting_priority)
    await message.answer("Укажите приоритет:", reply_markup=priority_kb(data["role"]))


@router.callback_query(AddObligation.waiting_priority, F.data.startswith("add:"))
async def add_priority(callback: CallbackQuery, state: FSMContext):
    priority_value = callback.data.split(":")[3]
    await state.update_data(priority=priority_value)
    await state.set_state(AddObligation.waiting_note)
    await callback.answer()
    await callback.message.edit_text(
        "Хотите добавить комментарий (например, за что долг)? Напишите текст или «Пропустить».",
        reply_markup=skip_kb("note"),
    )


@router.message(AddObligation.waiting_note)
async def add_note(message: Message, state: FSMContext):
    await state.update_data(note=message.text.strip())
    await _finish_add(message, state)


@router.callback_query(AddObligation.waiting_note, F.data == "skip:note")
async def skip_note(callback: CallbackQuery, state: FSMContext):
    await state.update_data(note=None)
    await callback.answer()
    await _finish_add(callback.message, state)


async def _finish_add(message: Message, state: FSMContext):
    data = await state.get_data()
    role = data["role"]
    with SessionLocal() as session:
        try:
            obligation = create_obligation(
                session,
                user_id=message.chat.id,
                role=_role_enum(role),
                counterparty_name=data["counterparty_name"],
                amount=data["amount"],
                due_date=dt.datetime.fromisoformat(data["due_date"]),
                priority=Priority(data["priority"]),
                interest_rate=data.get("interest_rate"),
                note=data.get("note"),
            )
        except ValueError as e:
            # Подстраховка: сюда попадём, только если пользователь как-то обошёл
            # пошаговую валидацию в хендлерах (например, гонка состояний).
            await state.clear()
            await message.answer(f"Не удалось сохранить запись: {e}")
            return
    await state.clear()
    noun = ROLE_LABELS[role]["noun"]
    await message.answer(
        f"✅ Запись сохранена: {noun} — {data['counterparty_name']}, {data['amount']:g}.\n"
        f"Напоминания включены по умолчанию (за 3 дня до срока, 1 раз). "
        f"Настроить можно в карточке записи.",
        reply_markup=role_menu_kb(role),
    )


# ---------- UC3: список обязательств ----------

@router.callback_query(F.data.startswith("role:") & F.data.contains(":list"))
async def show_list(callback: CallbackQuery):
    role = callback.data.split(":")[1]
    with SessionLocal() as session:
        items = list_obligations(session, callback.from_user.id, _role_enum(role))
        if not items:
            await callback.message.edit_text(
                "Записей пока нет.", reply_markup=role_menu_kb(role)
            )
            await callback.answer()
            return

        lines = [f"Список ({ROLE_LABELS[role]['noun_plural']}):\n"]
        buttons_data = []
        for o in items:
            rem = remaining_amount(o)
            status_icon = {"active": "🟢", "closed": "✅", "overdue": "🔴"}[o.status.value]
            lines.append(
                f"{status_icon} #{o.id} {o.counterparty_name} — остаток {rem:g}, "
                f"срок {o.due_date.date():%d.%m.%Y}, приоритет {o.priority.value}"
            )
            buttons_data.append(o.id)

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    b = InlineKeyboardBuilder()
    for oid in buttons_data:
        b.button(text=f"Открыть #{oid}", callback_data=f"open:{role}:{oid}")
    b.button(text="⬅️ Назад", callback_data=f"menu:role:{role}")
    b.adjust(2)

    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("open:"))
async def open_item(callback: CallbackQuery):
    _, role, oid = callback.data.split(":")
    with SessionLocal() as session:
        obligation = get_obligation(session, int(oid))
        if obligation is None:
            await callback.answer("Запись не найдена (возможно, удалена).", show_alert=True)
            return
        rem = remaining_amount(obligation)
        interest = estimate_accrued_interest(obligation)
        rule = obligation.reminder_rule
        text = (
            f"Запись #{obligation.id}\n"
            f"Контрагент: {obligation.counterparty_name}\n"
            f"Сумма: {obligation.amount:g} (остаток: {rem:g})\n"
            f"Ставка: {obligation.interest_rate or 0:g}% годовых "
            f"(ориент. набежало: {interest:g})\n"
            f"Срок: {obligation.due_date.date():%d.%m.%Y}\n"
            f"Приоритет: {obligation.priority.value}\n"
            f"Статус: {obligation.status.value}\n"
            f"Напоминания: {'включены' if rule.enabled else 'выключены'} "
            f"(за {rule.days_before} дн., {rule.sent_count}/{rule.repeat_times} отправлено)\n"
            + (f"Комментарий: {obligation.note}\n" if obligation.note else "")
        )
    await callback.message.edit_text(text, reply_markup=obligation_item_kb(int(oid), role))
    await callback.answer()


@router.callback_query(F.data.startswith("del:"))
async def delete_item(callback: CallbackQuery):
    oid = int(callback.data.split(":")[1])
    with SessionLocal() as session:
        obligation = get_obligation(session, oid)
        if obligation is None:
            await callback.answer("Уже удалено.", show_alert=True)
            return
        role = obligation.role.value
        delete_obligation(session, obligation)
    await callback.answer("Запись удалена.")
    await callback.message.edit_text("Запись удалена.", reply_markup=role_menu_kb(role))


# ---------- UC4: внесение платежа ----------

@router.callback_query(F.data.startswith("pay:"))
async def start_payment(callback: CallbackQuery, state: FSMContext):
    oid = int(callback.data.split(":")[1])
    await state.update_data(obligation_id=oid)
    await state.set_state(AddPayment.waiting_amount)
    await callback.message.edit_text("Введите сумму платежа:")
    await callback.answer()


@router.message(AddPayment.waiting_amount)
async def finish_payment(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Нужно положительное число. Попробуйте ещё раз:")
        return

    data = await state.get_data()
    oid = data["obligation_id"]
    with SessionLocal() as session:
        obligation = get_obligation(session, oid)
        if obligation is None:
            await state.clear()
            await message.answer("Запись не найдена (возможно, удалена).")
            return
        try:
            add_payment(session, obligation, amount)
        except ValueError as e:
            # Остаёмся в том же состоянии FSM — пользователь просто вводит сумму заново,
            # не нужно начинать сценарий внесения платежа с начала.
            await message.answer(f"{e} Введите другую сумму:")
            return
        role = obligation.role.value
        rem = remaining_amount(obligation)
        status = obligation.status.value

    await state.clear()
    status_text = "Обязательство полностью закрыто ✅" if status == "closed" else f"Остаток: {rem:g}"
    await message.answer(f"Платёж {amount:g} зафиксирован.\n{status_text}", reply_markup=back_to_list_kb(role))