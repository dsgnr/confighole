FROM python:3.13-alpine AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_VER=2.2.1

# Install Poetry
RUN pip install --no-cache-dir poetry==$POETRY_VER

WORKDIR /app

COPY pyproject.toml poetry.lock ./

# Install only main dependencies
RUN poetry install --no-cache --only=main --no-root --no-ansi

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

# Copy confighole
COPY confighole confighole

RUN chown -R confighole:confighole /app

USER confighole

ENTRYPOINT ["python", "-m", "confighole.cli"]
