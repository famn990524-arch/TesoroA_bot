FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY TesoroA_bot.py .

CMD ["python", "TesoroA_bot.py"]