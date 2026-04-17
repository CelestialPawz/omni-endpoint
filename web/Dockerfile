FROM python:3.11-slim

WORKDIR /app

COPY ../requirements.txt .
RUN pip install --no-cache-dir flask requests python-dotenv aiosqlite

COPY web/ .
COPY database.py .

EXPOSE 5000

CMD ["python", "app.py"]
