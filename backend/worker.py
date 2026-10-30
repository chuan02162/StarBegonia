"""RQ worker + optional Sydney-midnight sequential source sync scheduler."""

from __future__ import annotations

import logging
import os

from redis import Redis
from rq import Worker

from app import create_app
from app.jobs.scheduler import start_daily_sync_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def main() -> None:
    app = create_app()
    with app.app_context():
        start_daily_sync_scheduler(app)
        from app.jobs.queues import WORKER_QUEUES

        conn = Redis.from_url(app.config["REDIS_URL"])
        queue_names = [
            name.strip()
            for name in os.environ.get("RQ_QUEUES", ",".join(WORKER_QUEUES)).split(",")
            if name.strip()
        ]
        worker = Worker(queue_names, connection=conn)
        worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
