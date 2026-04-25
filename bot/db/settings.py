"""
Настройки бота (key-value).
"""

from dataclasses import dataclass

import aiosqlite

from bot.config import (
    DEFAULT_DAYS_N, THRESHOLD_A, THRESHOLD_B, THRESHOLD_C,
    DEFAULT_REFILL_RESERVE_PCT, REFILL_PERIOD_DAYS,
)
from bot.db.connection import get_connection


@dataclass(frozen=True)
class CalcParams:
    days_threshold: int
    threshold_a: float
    threshold_b: float
    threshold_c: float
    refill_reserve_pct: int
    refill_period_days: int


async def get_calc_params() -> CalcParams:
    """Загружает все параметры расчёта из настроек БД."""
    return CalcParams(
        days_threshold=int(await get_setting('calc_days_threshold', str(DEFAULT_DAYS_N))),
        threshold_a=float(await get_setting('calc_threshold_a', str(THRESHOLD_A))),
        threshold_b=float(await get_setting('calc_threshold_b', str(THRESHOLD_B))),
        threshold_c=float(await get_setting('calc_threshold_c', str(THRESHOLD_C))),
        refill_reserve_pct=int(await get_setting('refill_reserve_pct', str(DEFAULT_REFILL_RESERVE_PCT))),
        refill_period_days=int(await get_setting('refill_period_days', str(REFILL_PERIOD_DAYS))),
    )


async def get_setting(key: str, default: str = None) -> str | None:
    """Получает настройку по ключу."""
    db = await get_connection()
    cursor = await db.execute(
        'SELECT value FROM settings WHERE key = ?',
        (key,)
    )
    row = await cursor.fetchone()
    return row[0] if row else default


async def set_setting(key: str, value: str):
    """Сохраняет настройку (insert or replace)."""
    db = await get_connection()
    await db.execute(
        'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
        (key, value)
    )
    await db.commit()
