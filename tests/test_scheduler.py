from unittest.mock import MagicMock
from src.core.scheduler import AgentScheduler


def test_scheduler_creation():
    scheduler = AgentScheduler()
    assert scheduler is not None


def test_add_proactive_task():
    scheduler = AgentScheduler()
    cb = MagicMock()
    scheduler.add_proactive_task(
        task_id="morning_greeting",
        contact="张三",
        cron="0 9 * * 1-5",
        topic_hint="早安",
        callback=cb,
    )
    jobs = scheduler.list_jobs()
    assert "morning_greeting" in [j["id"] for j in jobs]


def test_add_supervisor_task():
    scheduler = AgentScheduler()
    cb = MagicMock()
    scheduler.add_supervisor_task(
        interval_cron="0 */6 * * *",
        callback=cb,
    )
    jobs = scheduler.list_jobs()
    assert any(j["id"] == "supervisor" for j in jobs)


def test_remove_task():
    scheduler = AgentScheduler()
    cb = MagicMock()
    scheduler.add_proactive_task("test_task", "张三", "0 9 * * *", "测试", cb)
    scheduler.remove_task("test_task")
    jobs = scheduler.list_jobs()
    assert "test_task" not in [j["id"] for j in jobs]
