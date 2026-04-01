from __future__ import annotations

from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


class AgentScheduler:
    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler()

    def start(self) -> None:
        self._scheduler.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    def add_proactive_task(
        self,
        task_id: str,
        contact: str,
        cron: str,
        topic_hint: str,
        callback: Callable,
    ) -> None:
        trigger = CronTrigger.from_crontab(cron)
        self._scheduler.add_job(
            callback,
            trigger=trigger,
            id=task_id,
            kwargs={"contact": contact, "topic_hint": topic_hint},
            replace_existing=True,
        )
        logger.info("Added proactive task '{}' for {} ({})", task_id, contact, cron)

    def add_supervisor_task(
        self,
        interval_cron: str,
        callback: Callable,
    ) -> None:
        trigger = CronTrigger.from_crontab(interval_cron)
        self._scheduler.add_job(
            callback,
            trigger=trigger,
            id="supervisor",
            replace_existing=True,
        )
        logger.info("Added supervisor task ({})", interval_cron)

    def remove_task(self, task_id: str) -> None:
        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass

    def list_jobs(self) -> list[dict]:
        return [{"id": job.id, "next_run": str(getattr(job, "next_run_time", None))} for job in self._scheduler.get_jobs()]
