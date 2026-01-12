FROM python:3.13-alpine AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VER=2.2.1

WORKDIR /app

RUN apk add --no-cache git \
    && pip install --no-cache-dir poetry==$POETRY_VER

COPY pyproject.toml poetry.lock ./

RUN poetry install --only=main --no-root --no-cache

FROM python:3.13-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/.venv/lib/python3.13/site-packages"

RUN addgroup -S confighole && adduser -S confighole -G confighole

WORKDIR /app

COPY --from=builder $PYTHONPATH $PYTHONPATH

COPY --chown=confighole:confighole confighole confighole

USER confighole

ENTRYPOINT ["python", "-m", "confighole.cli"]
