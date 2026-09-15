FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# System deps for asyncpg/psycopg builds (cached layer)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
  && rm -rf /var/lib/apt/lists/*

COPY server/pyproject.toml server/alembic.ini ./
COPY server/app ./app
COPY server/alembic ./alembic
COPY server/main.py ./main.py

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic \
  pydantic pydantic-settings email-validator pyjwt "pwdlib[bcrypt]" aiomqtt httpx \
  structlog python-multipart "psycopg[binary]"

# Non-root runtime user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready').read()"

# Run migrations then start the API (single worker; scale via Render instances)
CMD ["sh", "-c", "python -m alembic upgrade head && python main.py --host 0.0.0.0 --port 8000"]
