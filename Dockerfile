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

# --- Asset stage: build the CSS with the Tailwind standalone CLI (no Node needed) -
FROM python:3.14-slim AS assets

ARG TAILWIND_VERSION=3.4.16
ARG TARGETARCH
WORKDIR /app
RUN set -eu; \
    case "${TARGETARCH:-$(dpkg --print-architecture)}" in \
      amd64) arch=x64;   sha=33f254b54c8754f16efbe2be1de38ca25192630dc36f164595a770d4bbf4d893 ;; \
      arm64) arch=arm64; sha=1e6746bba6f3d34d7550889a1a009ab90ee3794a5ebce60ed10688ad10680a87 ;; \
      *) echo "Unsupported architecture" >&2; exit 1 ;; \
    esac; \
    python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" \
      "https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-${arch}" \
      /usr/local/bin/tailwindcss; \
    echo "${sha}  /usr/local/bin/tailwindcss" | sha256sum -c -; \
    chmod +x /usr/local/bin/tailwindcss
COPY frontend frontend
COPY templates templates
RUN tailwindcss -c frontend/tailwind.config.js -i frontend/app.css -o static/css/app.css --minify

# --- Runtime stage: only venv and code, without Poetry ---------------------------
FROM python:3.14-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_CONCURRENCY=3

# curl for the healthcheck (also used by Coolify).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 1000 --home /app app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=app:app . .
COPY --from=assets --chown=app:app /app/static/css static/css
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && chmod +x docker/entrypoint.sh

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/ || exit 1
ENTRYPOINT ["docker/entrypoint.sh"]
# Gunicorn reads the number of workers from WEB_CONCURRENCY.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--access-logfile", "-"]
