# Wildberries API - Полный справочник endpoints

Документ создан на основе официальной документации Wildberries API (dev.wildberries.ru).
Дата актуализации: Февраль 2026.
Последняя проверка endpoints: 02.02.2026

---

## Авторизация

Для авторизации всех запросов к WB API необходим API-токен (JWT).

**Формат заголовка:**
```
Authorization: {ваш_токен}
```

**Типы токенов:**
| Категория | Описание |
|-----------|----------|
| Content | Карточки товаров, цены, остатки |
| Marketplace | Заказы FBS, поставки, склады |
| Statistics | Статистика продаж, заказов |
| Analytics | Аналитика, воронки, поисковые запросы |
| Promotions | Рекламные кампании, акции |
| Feedbacks & Questions | Отзывы и вопросы |
| Supplies | Поставки FBW |
| Returns | Возвраты |
| Finance | Финансы и баланс |
| Documents | Документы и акты |

---

## Базовые URL

| Категория | URL |
|-----------|-----|
| Common API | `https://common-api.wildberries.ru` |
| Content API | `https://content-api.wildberries.ru` |
| Analytics API | `https://seller-analytics-api.wildberries.ru` |
| Statistics API | `https://statistics-api.wildberries.ru` |
| Prices & Discounts | `https://discounts-prices-api.wildberries.ru` |
| Marketplace API | `https://marketplace-api.wildberries.ru` |
| Supplies API (FBW) | `https://supplies-api.wildberries.ru` |
| Feedbacks API | `https://feedbacks-api.wildberries.ru` |
| Questions API | `https://questions-api.wildberries.ru` |
| Buyer Chat API | `https://buyer-chat-api.wildberries.ru` |
| Returns API | `https://returns-api.wildberries.ru` |
| Promotions API | `https://advert-api.wildberries.ru` |
| Finance API | `https://finance-api.wildberries.ru` |
| Documents API | `https://documents-api.wildberries.ru` |
| User Management | `https://user-management-api.wildberries.ru` |

---

## 1. Common API (Общие методы)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://common-api.wildberries.ru`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/ping` | Проверка соединения (лимит: 3 запроса / 30 сек) |
| GET | `/api/v1/seller-info` | Информация о продавце (лимит: 1 запрос / мин) |
| GET | `/api/communications/v2/news` | Новости WB (лимит: 1 запрос / мин) |
| GET | `/api/v1/tariffs/commission` | Комиссии по категориям (лимит: 1 запрос / мин) |
| GET | `/api/v1/tariffs/box` | Тарифы на логистику коробов (лимит: 60 запросов / мин) |
| GET | `/api/v1/tariffs/pallet` | Тарифы на логистику паллет (лимит: 60 запросов / мин) |
| GET | `/api/v1/tariffs/return` | Тарифы на возврат (лимит: 60 запросов / мин) |
| GET | `/api/tariffs/v1/acceptance/coefficients` | Коэффициенты приёмки на ближайшие 14 дней (лимит: 6 запросов / 10 сек) |

> **Примечание:** Endpoint `/api/v1/tariffs/storage` удалён из Common API.

---

## 2. User Management API (Управление пользователями)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://user-management-api.wildberries.ru`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| DELETE | `/api/v1/user` | Удаление пользователя из списка |
| PATCH | `/api/v1/users/accesses` | Изменение прав доступа пользователей |

> **Примечание:** Требуется Personal токен с категорией Users. Управление доступом только для владельца аккаунта.

---

## 3. Content API (Карточки товаров)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://content-api.wildberries.ru`

### Категории и справочники
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/content/v2/object/parent/all` | Родительские категории |
| GET | `/content/v2/object/all` | Список предметов (subjects) |
| GET | `/content/v2/object/charcs/{subjectId}` | Характеристики категории |
| GET | `/content/v2/directory/colors` | Справочник цветов |
| GET | `/content/v2/directory/kinds` | Справочник полов |
| GET | `/content/v2/directory/countries` | Справочник стран |
| GET | `/content/v2/directory/seasons` | Справочник сезонов |
| GET | `/content/v2/directory/vat` | Справочник ставок НДС |
| GET | `/content/v2/directory/tnved` | Справочник ТНВЭД |
| GET | `/api/content/v1/brands` | Справочник брендов по предмету |

### Карточки товаров
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/content/v2/cards/limits` | Лимиты на создание |
| POST | `/content/v2/barcodes` | Генерация SKU/штрихкодов |
| POST | `/content/v2/cards/upload` | Создание карточек (лимит: 10 запросов / мин) |
| POST | `/content/v2/cards/upload/add` | Создание с объединением (лимит: 10 запросов / мин) |
| POST | `/content/v2/get/cards/list` | Список карточек (курсор) |
| POST | `/content/v2/cards/error/list` | Ошибки карточек |
| POST | `/content/v2/cards/update` | Обновление карточек (лимит: 10 запросов / мин) |
| POST | `/content/v2/cards/moveNm` | Объединение/разъединение карточек |
| POST | `/content/v2/cards/delete/trash` | Перемещение в корзину |
| POST | `/content/v2/cards/recover` | Восстановление из корзины |
| POST | `/content/v2/get/cards/trash` | Список карточек в корзине |

### Медиафайлы
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/content/v3/media/file` | Загрузка медиафайла |
| POST | `/content/v3/media/save` | Загрузка медиа по ссылкам |

### Теги
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/content/v2/tags` | Список тегов |
| POST | `/content/v2/tag` | Создание тега |
| PATCH | `/content/v2/tag/{id}` | Обновление тега |
| DELETE | `/content/v2/tag/{id}` | Удаление тега |
| POST | `/content/v2/tag/nomenclature/link` | Управление привязкой товаров к тегам |

> **Примечание:** Лимит 100 запросов/мин для общих методов. Методы создания/редактирования карточек — 10 запросов/мин каждый. Максимум 3000 карточек в одном запросе.

---

## 4. Prices & Discounts API (Цены и скидки)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://discounts-prices-api.wildberries.ru`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v2/list/goods/filter` | Список товаров с ценами (поддержка сортировки) |
| GET | `/api/v2/list/goods/size/nm` | Цены по размерам |
| POST | `/api/v2/upload/task` | Загрузка цен (макс. 1000 товаров) |
| GET | `/api/v2/upload/task/{uploadId}` | Статус загрузки (коды: 3-ОК, 4-отмена, 5/6-ошибки) |
| GET | `/api/v2/history/goods/size/nm` | История изменения цен |
| GET | `/api/v2/quarantine/goods` | Товары в карантине цен |

> **Лимит:** 10 запросов / 6 сек на все методы. При снижении цены более чем в 3 раза — товар в карантине.

### Календарь акций WB
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/calendar/promotions` | Список доступных акций |
| GET | `/api/v1/calendar/promotions/details` | Детали акции |
| GET | `/api/v1/calendar/promotions/nomenclatures` | Товары для участия в акции |
| POST | `/api/v1/calendar/promotions/upload` | Добавить товар в акцию |

---

## 5. Analytics API (Аналитика)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://seller-analytics-api.wildberries.ru`

### Воронка продаж (Sales Funnel) — v3
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/analytics/v3/sales-funnel/products` | Статистика карточек за период |
| POST | `/api/analytics/v3/sales-funnel/products/history` | История по дням/неделям |
| POST | `/api/analytics/v3/sales-funnel/grouped/history` | Сгруппированная история |

### Поисковые запросы (Search Report)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/v2/search-report/report` | Основной отчёт по поиску |
| POST | `/api/v2/search-report/table/groups` | Пагинация по группам |
| POST | `/api/v2/search-report/table/details` | Пагинация по товарам |
| POST | `/api/v2/search-report/product/search-texts` | Топ запросов по товару |
| POST | `/api/v2/search-report/product/orders` | Заказы и позиции по запросу |

### Отчёт по остаткам (Stocks Report)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/v2/stocks-report/products/groups` | Остатки по группам |
| POST | `/api/v2/stocks-report/products/products` | Остатки по товарам |
| POST | `/api/v2/stocks-report/products/sizes` | Остатки по размерам |
| POST | `/api/v2/stocks-report/offices` | Остатки по складам |

### Удержания и штрафы
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/analytics/v1/measurement-penalties` | Штрафы за обмеры |
| GET | `/api/analytics/v1/warehouse-measurements` | Данные обмеров |
| GET | `/api/analytics/v1/deductions` | Удержания |
| GET | `/api/v1/analytics/antifraud-details` | Антифрод детализация |
| GET | `/api/v1/analytics/goods-labeling` | Стоимость маркировки |

### CSV отчёты (Seller Analytics)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/v2/nm-report/downloads` | Создать CSV отчёт |
| GET | `/api/v2/nm-report/downloads` | Список отчётов |
| POST | `/api/v2/nm-report/downloads/retry` | Перегенерировать отчёт |
| GET | `/api/v2/nm-report/downloads/file/{downloadId}` | Скачать ZIP с CSV |

> **Примечание:** Данные по остаткам обновляются каждые 30 минут. Отчёты доступны 48 часов после генерации.

---

## 6. Statistics API (Статистика)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://statistics-api.wildberries.ru`

| Метод | Endpoint | Параметры | Описание |
|-------|----------|-----------|----------|
| GET | `/api/v1/supplier/incomes` | `dateFrom` | ⚠️ **DEPRECATED** (удаление 11.03.2026) Поставки на склады WB |
| GET | `/api/v1/supplier/stocks` | `dateFrom` | Остатки на складах |
| GET | `/api/v1/supplier/orders` | `dateFrom`, `flag` | Заказы (flag=0 FBS, flag=1 все) |
| GET | `/api/v1/supplier/sales` | `dateFrom` | Продажи и возвраты |

### Остатки на складах WB (Warehouse Remains)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/warehouse_remains` | Создать задачу на отчёт |
| GET | `/api/v1/warehouse_remains/tasks/{task_id}/status` | Статус задачи |
| GET | `/api/v1/warehouse_remains/tasks/{task_id}/download` | Скачать отчёт |

**Примеры:**
```bash
# Продажи за январь
GET /api/v1/supplier/sales?dateFrom=2026-01-01

# Заказы
GET /api/v1/supplier/orders?dateFrom=2026-01-01&flag=1

# Остатки
GET /api/v1/supplier/stocks?dateFrom=2026-01-01
```

> **Лимит:** 1 запрос в минуту. История остатков не хранится — только realtime данные.

---

## 7. Reports API (Отчёты)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://seller-analytics-api.wildberries.ru`

### Отчёты по удержаниям
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/analytics/v1/measurement-penalties` | Штрафы за обмеры |
| GET | `/api/analytics/v1/warehouse-measurements` | Данные обмеров на складах |
| GET | `/api/analytics/v1/deductions` | Удержания |
| GET | `/api/v1/analytics/antifraud-details` | Антифрод детализация |
| GET | `/api/v1/analytics/goods-labeling` | Стоимость маркировки |

### Отчёт по акцизам (обязательная маркировка)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/v1/analytics/excise-report` | Отчёт по маркированным товарам |

### Финансовые отчёты (Finance API)
**Base URL:** `https://finance-api.wildberries.ru`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/account/balance` | Баланс и доступно к выводу |
| GET | `/api/v5/supplier/reportDetailByPeriod` | Отчёт реализации (лимит: 1 запрос / 5 мин) |

---

## 8. Marketplace API (FBS заказы, сборка)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://marketplace-api.wildberries.ru`

### Заказы FBS
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v3/orders/new` | Новые сборочные задания |
| GET | `/api/v3/orders` | Все заказы с пагинацией |
| POST | `/api/v3/orders/status` | Статусы конкретных заказов |
| GET | `/api/v3/supplies/orders/reshipment` | Заказы на повторную отгрузку |
| PATCH | `/api/v3/orders/{orderId}/cancel` | Отменить заказ |
| POST | `/api/v3/orders/stickers` | Стикеры (разные форматы) |
| POST | `/api/v3/orders/stickers/cross-border` | PDF стикеры для кросс-бордер |
| POST | `/api/v3/orders/status/history` | История статусов |
| POST | `/api/v3/orders/client` | Данные клиента (Турция) |

### Метаданные заказов (маркировка)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/marketplace/v3/orders/meta` | Получить метаданные |
| DELETE | `/api/v3/orders/{orderId}/meta` | Удалить метаданные |
| PUT | `/api/v3/orders/{orderId}/meta/sgtin` | Добавить Data Matrix (до 100 кодов) |
| PUT | `/api/v3/orders/{orderId}/meta/uin` | Добавить УИН |
| PUT | `/api/v3/orders/{orderId}/meta/imei` | Добавить IMEI |
| PUT | `/api/v3/orders/{orderId}/meta/gtin` | Добавить GTIN |
| PUT | `/api/v3/orders/{orderId}/meta/expiration` | Сроки годности |
| PUT | `/api/marketplace/v3/orders/{orderId}/meta/customs-declaration` | ГТД номера |

### Поставки FBS (Supplies)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/v3/supplies` | Создать поставку |
| GET | `/api/v3/supplies` | Список поставок |
| PATCH | `/api/marketplace/v3/supplies/{supplyId}/orders` | Добавить заказы (до 100 шт) |
| GET | `/api/v3/supplies/{supplyId}` | Информация о поставке |
| DELETE | `/api/v3/supplies/{supplyId}` | Удалить поставку |
| GET | `/api/marketplace/v3/supplies/{supplyId}/order-ids` | ID заказов в поставке |
| PATCH | `/api/v3/supplies/{supplyId}/deliver` | Передать в доставку |
| GET | `/api/v3/supplies/{supplyId}/barcode` | QR-код поставки |

### Короба
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v3/supplies/{supplyId}/trbx` | Список коробов |
| POST | `/api/v3/supplies/{supplyId}/trbx` | Добавить короба |
| DELETE | `/api/v3/supplies/{supplyId}/trbx` | Удалить короба |
| POST | `/api/v3/supplies/{supplyId}/trbx/stickers` | Стикеры коробов |

### Пропуска
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v3/passes/offices` | Склады для пропусков |
| GET | `/api/v3/passes` | Список пропусков |
| POST | `/api/v3/passes` | Создать пропуск |
| PUT | `/api/v3/passes/{passId}` | Обновить пропуск |
| DELETE | `/api/v3/passes/{passId}` | Удалить пропуск |

> **Sandbox:** `https://marketplace-api-sandbox.wildberries.ru` для тестирования.

---

## 9. Warehouses API (Склады)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://marketplace-api.wildberries.ru`

### Склады продавца
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v3/warehouses` | Список складов продавца |
| POST | `/api/v3/warehouses` | Создать склад |
| PUT | `/api/v3/warehouses/{warehouseId}` | Обновить склад (смена офиса 1 раз/день) |
| DELETE | `/api/v3/warehouses/{warehouseId}` | Удалить склад |
| GET | `/api/v3/offices` | Склады WB для привязки |

### Остатки FBS
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v3/stocks/{warehouseId}` | Остатки на складе продавца |
| PUT | `/api/v3/stocks/{warehouseId}` | Обновить остатки |
| DELETE | `/api/v3/stocks/{warehouseId}` | Обнулить остатки |

> **Важно:** С 26.05.2025 нельзя обновлять остатки мелкогабарита (cargoType=1) на складах для крупногабарита.

---

## 10. Supplies API FBW (Поставки на склады WB)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://supplies-api.wildberries.ru`

### Информация для формирования поставок
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/acceptance/coefficients` | ⚠️ **DEPRECATED** Коэффициенты приёмки |
| POST | `/api/v1/acceptance/options` | Доступные склады и типы упаковки |
| GET | `/api/v1/warehouses` | Список складов WB |
| GET | `/api/v1/transit-tariffs` | Информация о транзитных направлениях |

### Управление поставками FBW
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/v1/supplies` | Список поставок (последние 1000 по умолчанию) |
| GET | `/api/v1/supplies/{ID}` | Детали поставки |
| GET | `/api/v1/supplies/{ID}/goods` | Товары в поставке |
| GET | `/api/v1/supplies/{ID}/package` | Штрихкод/упаковка поставки |

> **Лимит:** 6 запросов/мин. Приёмка доступна при coefficient=0 или 1 и allowUnload=true.

---

## 11. Tariffs API (Тарифы)
<!-- Проверено: 02.02.2026 — см. раздел 1. Common API -->

---

## 12. Feedbacks API (Отзывы)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://feedbacks-api.wildberries.ru`

### Отзывы
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/new-feedbacks-questions` | Непросмотренные отзывы и вопросы |
| GET | `/api/v1/feedbacks/count-unanswered` | Количество без ответа |
| GET | `/api/v1/feedbacks/count` | Общее количество отзывов |
| GET | `/api/v1/feedbacks` | Список с пагинацией |
| GET | `/api/v1/feedback` | Отзыв по ID |
| POST | `/api/v1/feedbacks/answer` | Ответить на отзыв |
| PATCH | `/api/v1/feedbacks/answer` | Редактировать ответ (1 раз за 60 дней) |
| POST | `/api/v1/feedbacks/order/return` | Запросить возврат товара |
| GET | `/api/v1/feedbacks/archive` | Архив отзывов |

### Закреплённые отзывы (Jam подписка)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/feedbacks/v1/pins` | Список закреплённых/незакреплённых |
| POST | `/api/feedbacks/v1/pins` | Закрепить отзыв |
| DELETE | `/api/feedbacks/v1/pins` | Открепить отзыв |
| GET | `/api/feedbacks/v1/pins/count` | Статистика закреплений |
| GET | `/api/feedbacks/v1/pins/limits` | Лимиты на закрепление |

> **Важно:** Шаблоны ответов отключены с 19.11.2025. Лимит: 3 запроса/сек.
> **Sandbox:** `https://feedbacks-api-sandbox.wildberries.ru`

---

## 13. Questions API (Вопросы)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://feedbacks-api.wildberries.ru`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/questions/count-unanswered` | Количество без ответа |
| GET | `/api/v1/questions/count` | Общее количество вопросов |
| GET | `/api/v1/questions` | Список с пагинацией |
| GET | `/api/v1/question` | Вопрос по ID |
| PATCH | `/api/v1/questions` | Просмотр/ответ/редактирование |

> **Примечание:** Вопросы и отзывы используют один base URL и общий лимит 3 запроса/сек.

---

## 14. Buyer Chat API (Чат с покупателями)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://buyer-chat-api.wildberries.ru`

### Чаты
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/chats` | Список всех чатов |
| GET | `/api/v1/chats/events` | События чатов (сообщения, isNewChat) |
| POST | `/api/v1/chats/{chatId}/messages` | Отправить сообщение |
| GET | `/api/v1/chats/{chatId}/messages/{messageId}/file` | Скачать файл/изображение |

### Заявки на возврат (из чата)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/returns` | Заявки на возврат за 14 дней |
| POST | `/api/v1/returns/{returnId}/answer` | Ответить на заявку |

> **Важно:** Объект refund удалён из событий чата. Фото в WEBP формате.

---

## 15. Returns API (Возвраты)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://returns-api.wildberries.ru`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/returns` | Список возвратов FBS |
| GET | `/api/v1/returns/{returnId}` | Детали возврата |
| POST | `/api/v1/returns/{returnId}/reject` | Отклонить возврат (код rejectcustom + comment) |

> **Примечание:** Фото возвратов теперь в формате WEBP (с 14.10.2024). Обработка заявок на возврат также доступна через Buyer Chat API.

---

## 16. Promotions API (Реклама и акции)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://advert-api.wildberries.ru`

### Управление кампаниями
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/adv/v1/promotion/count` | Кампании по типам/статусам |
| GET | `/api/advert/v2/adverts` | Информация о кампаниях |
| POST | `/adv/v2/seacat/save-ad` | Создать кампанию |
| GET | `/adv/v0/delete` | Удалить кампанию |
| POST | `/adv/v0/rename` | Переименовать |
| GET | `/adv/v0/start` | Запустить (статусы 4, 11) |
| GET | `/adv/v0/pause` | Приостановить |
| GET | `/adv/v0/stop` | Остановить |

### Ставки
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/advert/v1/bids/min` | Минимальные ставки |
| PATCH | `/api/advert/v1/bids` | Изменить ставки |
| PUT | `/adv/v0/auction/placements` | Настройки размещения |

### Кластеры поиска
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/adv/v0/normquery/get-bids` | Ставки по кластерам |
| POST | `/adv/v0/normquery/bids` | Установить ставки |
| DELETE | `/adv/v0/normquery/bids` | Удалить ставки |
| POST | `/adv/v0/normquery/get-minus` | Минус-фразы |
| POST | `/adv/v0/normquery/set-minus` | Настроить минус-фразы |
| POST | `/adv/v0/normquery/stats` | Статистика кластеров |

### Финансы рекламы
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/adv/v1/balance` | Баланс, бонусы, кешбэк |
| GET | `/adv/v1/budget` | Бюджет кампании |
| POST | `/adv/v1/budget/deposit` | Пополнить бюджет |
| GET | `/adv/v1/upd` | История расходов |
| GET | `/adv/v1/payments` | История пополнений |

### Статистика
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/adv/v2/fullstats` | Статистика кампаний |
| GET | `/adv/v3/fullstats` | Статистика v3 |
| POST | `/adv/v1/stats` | Статистика медиакампаний |

### Календарь акций WB
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/calendar/promotions` | Доступные акции |
| GET | `/api/v1/calendar/promotions/details` | Детали акции |
| GET | `/api/v1/calendar/promotions/nomenclatures` | Товары для акции |
| POST | `/api/v1/calendar/promotions/upload` | Добавить товар в акцию |

> **Синхронизация:** данные каждые 3 мин, статусы каждую 1 мин, ставки каждые 30 сек.
> **Sandbox:** `https://advert-api-sandbox.wildberries.ru`

---

## 17. Finance API (Финансы)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://finance-api.wildberries.ru`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/account/balance` | Баланс и доступная сумма к выводу |
| GET | `/api/v5/supplier/reportDetailByPeriod` | Отчёт о реализации (лимит: 1 запрос / 5 мин) |

> **Примечание:** Требуется токен категории Finance для баланса, Statistics для отчёта.

---

## 18. Documents API (Документы)
<!-- Проверено: 02.02.2026 -->

**Base URL:** `https://documents-api.wildberries.ru`

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/documents/categories` | Категории документов |
| GET | `/api/v1/documents/list` | Список документов (сортировка, пагинация) |
| GET | `/api/v1/documents/download` | Скачать один документ |
| POST | `/api/v1/documents/download/all` | Скачать несколько документов (batch) |

> **Примечание:** Требуется токен категории Documents.

---

## Лимиты запросов
<!-- Обновлено: 02.02.2026 -->

| API | Лимит | Примечание |
|-----|-------|------------|
| Statistics API | 1 запрос/мин | История не хранится |
| Content API | 100 запросов/мин общий | Создание/редактирование: 10/мин каждый |
| Analytics API | 10 запросов/мин | Отчёты доступны 48 часов |
| Marketplace API | 300 запросов/мин | — |
| Feedbacks/Questions API | 3 запроса/сек (6 burst) | — |
| Promotions API | 300 запросов/мин | — |
| Tariffs API (box/pallet/return) | 60 запросов/мин | Commission: 1/мин |
| Finance API (reportDetail) | 1 запрос/5 мин | — |
| Supplies API (FBW) | 6 запросов/мин | — |
| Prices API | 10 запросов/6 сек | — |

При превышении лимита возвращается **HTTP 429** с заголовком `X-Ratelimit-Retry` (секунды ожидания).

Алгоритм: **Token Bucket** — распределяйте запросы равномерно.

---

## Полезные ссылки

- [Официальная документация](https://dev.wildberries.ru)
- [FAQ для разработчиков](https://dev.wildberries.ru/en/faq)
- [Новости API](https://dev.wildberries.ru/en/news)
- [Статусы серверов](https://status.wildberries.ru)

---

*Документ сгенерирован автоматически на основе официальной документации WB API.*
*Последнее обновление: 02.02.2026*
