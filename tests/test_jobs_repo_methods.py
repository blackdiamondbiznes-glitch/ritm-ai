from app.db.repositories.jobs import JobRepository


def test_health_counters_are_repository_methods():
    assert callable(getattr(JobRepository, "count_pending", None))
    assert callable(getattr(JobRepository, "count_failed_since", None))
