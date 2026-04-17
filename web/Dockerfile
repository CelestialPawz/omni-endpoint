FROM python:3.11-slim

WORKDIR /app

# Build context is repo root (set in docker-compose.yml)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web/ ./web/
COPY database.py .

WORKDIR /app/web

EXPOSE 5000

CMD ["python", "app.py"]
