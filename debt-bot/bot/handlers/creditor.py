"""
Явная точка входа ветки "Кредитор" — см. пояснение в bot/handlers/debtor.py.
Логика идентична ветке должника с точностью до роли (role=loan), поэтому
переиспользует общий router.
"""
from bot.handlers.obligations import router  # noqa: F401
