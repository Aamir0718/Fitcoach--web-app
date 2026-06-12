FROM python:3.11-slim

# Security: run as non-root
RUN useradd -m -u 1000 fitcoach
WORKDIR /app

# Install deps first (cached layer)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY backend/ .

# Data volume for SQLite DB
VOLUME ["/app/data"]
ENV DB_PATH=/app/data/users.db

# Don't run as root
USER fitcoach

EXPOSE 5000

# Production server — not flask dev server
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
