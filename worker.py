#!/usr/bin/env python3
"""Run the PDF TOC background worker."""

from redis import Redis
from rq import Worker

from backend_config import settings


if __name__ == "__main__":
    settings.ensure_dirs()
    redis_conn = Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5)
    worker = Worker([settings.queue_name], connection=redis_conn)
    worker.work(with_scheduler=True)
