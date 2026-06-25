FROM python:3.12-slim
WORKDIR /app

# Install deps directly (uv not available in this slim image)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi>=0.115 \
    "uvicorn[standard]>=0.30" \
    "sqlalchemy[asyncio]>=2.0" \
    asyncpg>=0.29 \
    alembic>=1.13 \
    pydantic-settings>=2.5 \
    email-validator>=2.1 \
    "python-jose[cryptography]>=3.3" \
    bcrypt>=4.1 \
    httpx>=0.27 \
    structlog>=24.4

COPY pyproject.toml .
COPY app/ ./app/
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/
COPY tests/ ./tests/

# Install as package so alembic can import app.models
RUN pip install -e . --no-deps --no-cache-dir

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
