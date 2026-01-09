FROM python:3.13-alpine AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=0 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_VER=2.2.1

# Build dependencies only
RUN apk add --no-cache --virtual .build-deps \
        build-base \
        git \
        libffi-dev \
        openssl-dev \
        python3-dev \
        musl-dev

# Install Poetry
RUN pip install --no-cache-dir poetry==$POETRY_VER

WORKDIR /app

COPY pyproject.toml poetry.lock ./

# Install only main dependencies
RUN poetry install --no-cache --only=main --no-root

COPY . .

# Clean up unnecessary files to reduce size
RUN find /usr/local/lib/python3.13/site-packages -type d \( -name "tests" -o -name "test" -o -name "__pycache__" -o -name "docs" \) -exec rm -rf {} + \
    && find /usr/local/lib/python3.13/site-packages -name "*.pyc" -delete \
    && rm -rf /root/.cache


FROM python:3.13-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user
RUN addgroup -S confighole && adduser -S confighole -G confighole

WORKDIR /app

# Copy only what is needed from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /app /app

RUN chown -R confighole:confighole /app

USER confighole

ENTRYPOINT ["python", "-m", "confighole.cli"]
