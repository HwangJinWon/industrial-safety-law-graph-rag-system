FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WATCH_DATABASE_PATH=/app/data/watch_data.db

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["sh", "-c", "exec python -m uvicorn main:app --app-dir app --host 0.0.0.0 --port \"${PORT:-8000}\""]
