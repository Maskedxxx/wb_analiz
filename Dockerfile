FROM python:3.11-slim

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Непривилегированный пользователь для безопасности
RUN groupadd -r botuser && useradd -r -g botuser -d /app -s /sbin/nologin botuser

# Копируем код
COPY bot/ bot/

# Создаём директории и даём права ДО смены пользователя
RUN mkdir -p /app/feedback /app/reports /app/data /app/logs \
    && chown -R botuser:botuser /app

USER botuser

# Запуск бота
CMD ["python", "-m", "bot.main"]
