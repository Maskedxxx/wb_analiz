# WB Analiz

## О проекте
Телеграм-бот для продавцов Wildberries. Мультимагазин, анализ остатков, рекомендации по ценам, сравнение магазинов.

## Стиль общения
Лаконично, чётко, по делу. Без воды.

## Правило работы
**Перед написанием любого кода** — сначала обсуждаем план и детали. Только после одобрения — реализация.

## Окружение
- **Сервер:** DGX Spark (ARM64)
- **Запуск:** Docker (`docker compose up -d`)
- **Локальная отладка:** `.venv/` в корне проекта, `run_local.sh`

## Доступы
- **Токены WB API:** хранятся в SQLite БД (`data/bot.db`), обфусцированные
- **Авторизация бота:** пароль `BOT_PASSWORD` в `.env`
- **Telegram:** `TELEGRAM_TOKEN` в `.env`

## Структура
```
wb_analiz/
├── CLAUDE.md
├── wb_api.py                         ← функции WB API
├── bot/
│   ├── __init__.py
│   ├── config.py                     ← настройки (env + дефолты)
│   ├── db.py                         ← SQLite (магазины, подписчики, кэш)
│   ├── main.py                       ← точка входа
│   ├── report.py                     ← генерация Excel-отчётов
│   ├── scheduler.py                  ← планировщик рассылки
│   ├── keyboards.py                  ← inline-клавиатуры
│   ├── states.py                     ← FSM состояния
│   ├── middleware.py                 ← авторизация + rate limiting
│   ├── security.py                   ← обфускация токенов, маскировка логов
│   └── handlers/
│       ├── __init__.py               ← регистрация роутеров
│       ├── menu.py                   ← главное меню, /start
│       ├── analysis.py               ← анализ остатков по магазину
│       ├── comparison.py             ← сравнение двух магазинов
│       ├── stores.py                 ← CRUD магазинов
│       ├── settings.py               ← настройки (время, пороги, подписка)
│       └── feedback.py               ← фидбек (эмодзи, комментарии)
├── docs/
│   └── WB_API_ENDPOINTS.md           ← справочник WB API endpoints
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── run_local.sh                      ← локальный запуск без Docker
├── .env.example
├── data/                             ← SQLite БД (volume)
├── reports/                          ← Excel-отчёты (volume)
├── feedback/                         ← CSV фидбек (volume)
└── logs/                             ← логи бота (volume)
```

## Магазины
| # | Бренд | Юрлицо |
|---|-------|--------|
| 1 | DobroDom | ИП Безруков Д. А. |
| 2 | Чина Шоп | ИП Егоров Д. В. |
| 3 | MODIN | ИП Модин И. В. |

## Запуск
```bash
# Docker (рекомендуется)
cp .env.example .env  # заполнить TELEGRAM_TOKEN
docker compose up -d --build

# Управление
docker compose logs -f     # логи
docker compose down        # остановить
docker compose restart     # перезапустить
```

## Что реализовано
- [x] Мультимагазин (добавление через бот или БД)
- [x] Анализ остатков с группировкой A/B/C
- [x] Рекомендации по повышению цены (шкала < 7 дней)
- [x] Сравнение магазинов по одинаковым товарам
- [x] Ежедневная рассылка Excel (09:00 МСК, APScheduler)
- [x] Авторизация по паролю, rate limiting
- [x] Обфускация токенов в БД, маскировка в логах
- [x] Docker с healthcheck и автоперезапуском
- [x] Очистка старых отчётов, логов, фидбека
