# Keep Python on 3.12 and use Bookworm's supported package repositories.
FROM python:3.12-slim-bookworm

# Prevents Python from writing .pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
# Ensures output is logged instantly (not buffered)
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
# Current deployment mode: FastAPI supervises the background workers inside
# the single Uvicorn process. Override to false only after deploying those
# workers separately.
ENV RUN_EMBEDDED_WORKERS=true

# Create working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose port (used in both dev and prod)
EXPOSE 8000

# Let the platform's SIGTERM reach Uvicorn directly so FastAPI lifespan can
# stop the embedded workers before shared connections are closed.
STOPSIGNAL SIGTERM

# One Uvicorn process owns the API and every supervised background service.
# Do not add `--workers` while RUN_EMBEDDED_WORKERS=true.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port ${APP_PORT:-8000}"]
