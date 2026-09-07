FROM python:3.12-slim

WORKDIR /app

# System deps needed by psycopg/asyncpg-adjacent wheels and cryptography's
# build backend on some platforms — kept minimal on purpose.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Runs pending migrations before every start, not just on first deploy —
# a fresh container on a host that already has an up-to-date DB just gets
# a fast no-op from alembic; one that's behind gets caught up automatically
# instead of booting against a schema the code doesn't match.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
