"""RQ worker entrypoint. M0: process ready; M2: enqueue Coles sync jobs here."""

from __future__ import annotations

from redis import Redis
from rq import Worker

from app import create_app


def main() -> None:
    app = create_app()
    with app.app_context():
        conn = Redis.from_url(app.config["REDIS_URL"])
        worker = Worker(["default"], connection=conn)
        worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
