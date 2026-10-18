# --- Build stage: install dependencies with Poetry into a venv -------------------
FROM python:3.14-slim AS builder

ENV POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install "poetry>=2,<3"
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

# --- Runtime stage: only venv and code, without Poetry ---------------------------
FROM python:3.14-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --system --uid 1000 --home /app app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=app:app . .
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && chmod +x docker/entrypoint.sh

USER app
EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
