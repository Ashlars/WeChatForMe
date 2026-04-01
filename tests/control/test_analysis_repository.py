from src.control.repositories.analysis_repository import AnalysisRepository
from src.core.context import ContextManager


def test_create_and_get_run(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = AnalysisRepository(ctx)

    run = repo.create_run(target_type="contact", target_id="wxid_1", trigger_type="manual")
    assert run["status"] == "queued"
    assert run["id"] is not None

    fetched = repo.get_run(run["id"])
    assert fetched["target_id"] == "wxid_1"


def test_get_run_not_found(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = AnalysisRepository(ctx)
    assert repo.get_run(999) is None


def test_mark_running(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = AnalysisRepository(ctx)

    run = repo.create_run(target_type="contact", target_id="wxid_1", trigger_type="manual")
    repo.mark_running(run["id"])
    assert repo.get_run(run["id"])["status"] == "running"
    assert repo.get_run(run["id"])["started_at"] is not None


def test_mark_succeeded(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = AnalysisRepository(ctx)

    run = repo.create_run(target_type="contact", target_id="wxid_1", trigger_type="manual")
    repo.mark_succeeded(run["id"], summary="OK", persona_json='{"p":1}', suggestions_json='{"s":1}')
    fetched = repo.get_run(run["id"])
    assert fetched["status"] == "succeeded"
    assert fetched["summary"] == "OK"
    assert fetched["persona_json"] == '{"p":1}'
    assert fetched["finished_at"] is not None


def test_mark_failed(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = AnalysisRepository(ctx)

    run = repo.create_run(target_type="contact", target_id="wxid_1", trigger_type="manual")
    repo.mark_failed(run["id"], error_message="API error")
    fetched = repo.get_run(run["id"])
    assert fetched["status"] == "failed"
    assert fetched["error_message"] == "API error"


def test_list_runs(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = AnalysisRepository(ctx)

    repo.create_run(target_type="contact", target_id="wxid_1", trigger_type="manual")
    repo.create_run(target_type="group", target_id="g1", trigger_type="scheduled")

    items, total = repo.list_runs()
    assert total == 2
    assert len(items) == 2


def test_list_runs_filter_by_target_type(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = AnalysisRepository(ctx)

    repo.create_run(target_type="contact", target_id="wxid_1", trigger_type="manual")
    repo.create_run(target_type="group", target_id="g1", trigger_type="scheduled")

    items, total = repo.list_runs(target_type="contact")
    assert total == 1
    assert items[0]["target_type"] == "contact"


def test_list_runs_filter_by_status(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = AnalysisRepository(ctx)

    run = repo.create_run(target_type="contact", target_id="wxid_1", trigger_type="manual")
    repo.mark_failed(run["id"], error_message="err")
    repo.create_run(target_type="contact", target_id="wxid_2", trigger_type="manual")

    items, total = repo.list_runs(status="queued")
    assert total == 1


def test_recover_stale(tmp_path):
    ctx = ContextManager(tmp_path / "test.db")
    repo = AnalysisRepository(ctx)

    run1 = repo.create_run(target_type="contact", target_id="wxid_1", trigger_type="manual")
    repo.mark_running(run1["id"])
    run2 = repo.create_run(target_type="contact", target_id="wxid_2", trigger_type="manual")

    recovered = repo.recover_stale()
    assert recovered == 2
    assert repo.get_run(run1["id"])["status"] == "failed"
    assert repo.get_run(run2["id"])["status"] == "failed"
    assert repo.get_run(run1["id"])["error_message"] == "worker_restarted"
