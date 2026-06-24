FROM python:3.11-slim

WORKDIR /app

COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/api/src/ ./src/
# Shared cleaning/term-extraction rules, vendored in at build time - see
# shared/preprocessing/ and docs/preprocessing.md. Edit that one module to
# change what the before/after preview shows; this Dockerfile never needs
# to change for it.
COPY shared/preprocessing/ ./src/preprocessing/

WORKDIR /app/src
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
