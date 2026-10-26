# The API for Railway (docs/deployment.md): migrations, then one Uvicorn process. One process on
# purpose: sign-ins in progress, running syncs and the log-in lock are kept in memory.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY backend/pyproject.toml backend/
COPY backend/app backend/app
RUN pip install ./backend
COPY backend/alembic.ini backend/
COPY backend/migrations backend/migrations

RUN useradd --create-home patterns && mkdir -p data && chown patterns data
USER patterns

# Railway sets PORT; its proxy terminates HTTPS in front of this process.
CMD ["sh", "-c", "alembic -c backend/alembic.ini upgrade head && exec uvicorn app.api.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
