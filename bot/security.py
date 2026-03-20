"""
Утилиты безопасности: обфускация токенов, хеширование паролей, маскировка в логах.
"""

import base64
import hashlib
import logging
import os
import re

# Ключ обфускации (XOR). Не криптография — защита от случайного чтения БД.
_OBF_KEY = os.getenv('TOKEN_OBF_KEY', 'wb-analiz-default-key').encode()


def obfuscate_token(token: str) -> str:
    """Обфусцирует токен (XOR + base64). Префикс 'obf:' помечает обработанные."""
    raw = token.encode()
    xored = bytes(b ^ _OBF_KEY[i % len(_OBF_KEY)] for i, b in enumerate(raw))
    return 'obf:' + base64.b64encode(xored).decode()


def deobfuscate_token(stored: str) -> str:
    """Деобфусцирует токен. Если нет префикса 'obf:' — возвращает как есть (миграция)."""
    if not stored.startswith('obf:'):
        return stored
    xored = base64.b64decode(stored[4:])
    raw = bytes(b ^ _OBF_KEY[i % len(_OBF_KEY)] for i, b in enumerate(xored))
    return raw.decode()


def hash_password(password: str) -> str:
    """SHA-256 хеш пароля для сравнения."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, expected: str) -> bool:
    """Сравнивает пароль с ожидаемым (plain или hash)."""
    return hash_password(password) == hash_password(expected)


def mask_token(token: str) -> str:
    """Маскирует токен для логов: первые 6 символов + ***."""
    if not token:
        return '***'
    clean = token.replace('obf:', '')
    return clean[:6] + '***' if len(clean) > 6 else '***'


# Паттерн для поиска длинных строк, похожих на токены (base64, JWT-подобные)
_TOKEN_PATTERN = re.compile(r'(eyJ[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{50,})')


class TokenMaskFilter(logging.Filter):
    """Logging filter: маскирует длинные строки, похожие на токены."""

    def filter(self, record):
        if record.args:
            record.msg = self._mask(str(record.msg))
            record.args = tuple(
                self._mask(str(a)) if isinstance(a, str) else a
                for a in record.args
            ) if isinstance(record.args, tuple) else record.args
        else:
            record.msg = self._mask(str(record.msg))
        return True

    @staticmethod
    def _mask(text: str) -> str:
        return _TOKEN_PATTERN.sub(lambda m: m.group()[:6] + '***', text)
