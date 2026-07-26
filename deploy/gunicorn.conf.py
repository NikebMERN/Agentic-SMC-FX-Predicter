import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
workers = int(os.getenv("WEB_CONCURRENCY", str(min(4, max(2, multiprocessing.cpu_count())))))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = int(os.getenv("GUNICORN_TIMEOUT_SECONDS", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT_SECONDS", "45"))
keepalive = 5
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "2000"))
max_requests_jitter = 200
accesslog = "-"
errorlog = "-"
capture_output = True
