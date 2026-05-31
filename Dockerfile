# GOOPHER backend container (Requirement T16) — deployable to Cloud Run (T14).
# Multi-stage keeps the final image small.

FROM python:3.12-slim AS base

# Avoid .pyc, get unbuffered logs (so Cloud Logging sees them immediately).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the application code + the storefront site (served at "/").
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY site/ ./site/

# Cloud Run injects $PORT (defaults to 8080); the app reads it.
ENV PORT=8080
EXPOSE 8080

# Non-root user for security.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

# Start the API. Single worker is fine for free-tier; scale via Cloud Run
# concurrency / instances. Uvicorn binds to 0.0.0.0:$PORT.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
