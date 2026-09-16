from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from bot.db import SessionLocal
from bot.keyboards import main_menu_kb, role_menu_kb
from bot.services.obligations import get_or_create_user, summary_for_user

router = Router(name="common")

ROLE_TITLES = {"debt": "🧾 Мои долги (я должен)", "loan": "💰 Мои займы (мне должны)"}


@router.message(CommandStart())
async def cmd_start(message: Message):
    with SessionLocal() as session:
        get_or_create_user(
            session,
            tg_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
    await message.answer(
        "Привет! Я помогу вести учёт долгов и займов и не забывать о датах платежей.\n\n"
        "Выберите раздел:",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "menu:root")
async def show_root_menu(callback: CallbackQuery):
    await callback.message.edit_text("Выберите раздел:", reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("menu:role:"))
async def show_role_menu(callback: CallbackQuery):
    role = callback.data.split(":")[2]  # "debt" | "loan"
    await callback.message.edit_text(ROLE_TITLES[role], reply_markup=role_menu_kb(role))
    await callback.answer()


@router.callback_query(F.data == "menu:summary")
async def show_summary(callback: CallbackQuery):
    with SessionLocal() as session:
        data = summary_for_user(session, callback.from_user.id)

    d, l = data["debts"], data["loans"]
    text = (
        "📊 Общая сводка\n\n"
        f"🧾 Мои долги: активных — {d['count_active']}, остаток — {d['remaining']:g}\n"
        f"   из них просрочено: {d['overdue_count']}\n"
        f"   ориентировочно набежало процентов: {d['accrued_interest']:g}\n\n"
        f"💰 Мне должны: активных — {l['count_active']}, остаток — {l['remaining']:g}\n"
        f"   из них просрочено: {l['overdue_count']}\n"
        f"   ориентировочно набежало процентов: {l['accrued_interest']:g}\n"
    )
    await callback.message.edit_text(text, reply_markup=main_menu_kb())
    await callback.answer()
