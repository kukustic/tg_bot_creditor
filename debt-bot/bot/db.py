"""
Слой подключения к БД.

Хранилище: SQLite. Выбрано намеренно, а не как заглушка — для демонстрационного
бота с одним процессом не нужен отдельный сервер БД, а сама база остаётся
одним файлом, который легко посмотреть/скопировать/сбросить при тестировании.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "debt_bot.db")
DB_URL = f"sqlite:///{Path(DB_PATH).resolve()}"

engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет. Импорт моделей должен произойти до вызова."""
    from bot import models  # noqa: F401  (регистрирует модели в Base.metadata)
    Base.metadata.create_all(bind=engine)
