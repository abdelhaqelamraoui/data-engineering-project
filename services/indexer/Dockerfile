FROM python:3.11-slim

WORKDIR /app

COPY services/indexer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/indexer/src/ ./src/
# Shared cleaning/term-extraction rules, vendored in at build time - see
# shared/preprocessing/ and docs/preprocessing.md. Edit that one module to
# change what gets indexed; this Dockerfile never needs to change for it.
COPY shared/preprocessing/ ./src/preprocessing/

WORKDIR /app/src
CMD ["python", "main.py"]
