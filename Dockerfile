FROM python:3.11-slim

WORKDIR /app

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY wb_api.py .
COPY bot/ bot/

# Создаём директории для данных
RUN mkdir -p /app/feedback /app/reports

# Запуск бота
CMD ["python", "-m", "bot.main"]
