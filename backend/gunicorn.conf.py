# gunicorn.conf.py — FitCoach AI production server config
# Run with: gunicorn -c gunicorn.conf.py app:app

import multiprocessing, os

# Workers: 2-4 × CPU cores is standard
workers     = int(os.getenv("WEB_CONCURRENCY", max(2, multiprocessing.cpu_count())))
worker_class = "sync"          # sync is fine for SQLite; switch to "gthread" with Postgres
threads     = 2                # threads per worker
timeout     = 120              # seconds before killing a stuck worker
keepalive   = 5

bind        = f"0.0.0.0:{os.getenv('PORT', '5000')}"
loglevel    = os.getenv("LOG_LEVEL", "info")
accesslog   = "-"              # stdout
errorlog    = "-"              # stderr

# Security
limit_request_line    = 4096
limit_request_fields  = 100
limit_request_field_size = 8190

# Graceful restart
graceful_timeout = 30
max_requests     = 1000        # recycle worker after N requests (prevents memory leaks)
max_requests_jitter = 100
