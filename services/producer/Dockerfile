FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /data && chmod 777 /data
VOLUME ["/data"]

WORKDIR /app/src
CMD ["python", "main.py"]
