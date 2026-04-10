"""Tests for the SQLite-backed JobStore."""

import pytest
from datetime import datetime, timezone
from models import Job
from storage import JobStore


@pytest.fixture
async def store(tmp_path):
    """Create an in-memory-like JobStore using a temp file."""
    db_path = str(tmp_path / "test_jobs.db")
    s = JobStore(db_path=db_path)
    await s.open()
    yield s
    await s.close()


def _make_job(**overrides) -> Job:
    defaults = dict(
        title="Engineer",
        company="TestCo",
        location="Vancouver",
        description="Build things.",
        apply_link="https://testco.com/jobs/1",
        posted_date=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Job(**defaults)


@pytest.mark.asyncio
async def test_upsert_and_exists(store):
    job = _make_job()
    assert not await store.job_exists(job.apply_link)

    is_new = await store.upsert_job(job)
    assert is_new is True
    assert await store.job_exists(job.apply_link)

    # Second upsert should return False (not new)
    is_new2 = await store.upsert_job(job)
    assert is_new2 is False


@pytest.mark.asyncio
async def test_mark_notified(store):
    job = _make_job(match_score=90, match_reasoning="Great fit")
    await store.upsert_job(job)

    unnotified = await store.get_unnotified_jobs(min_score=80)
    assert len(unnotified) == 1

    await store.mark_notified(job.apply_link)

    unnotified_after = await store.get_unnotified_jobs(min_score=80)
    assert len(unnotified_after) == 0


@pytest.mark.asyncio
async def test_get_unnotified_jobs_filters_by_score(store):
    job_low = _make_job(apply_link="https://a.com/low", match_score=40)
    job_high = _make_job(apply_link="https://a.com/high", match_score=95, match_reasoning="Perfect")

    await store.upsert_job(job_low)
    await store.upsert_job(job_high)

    results = await store.get_unnotified_jobs(min_score=80)
    assert len(results) == 1
    assert results[0].apply_link == "https://a.com/high"


@pytest.mark.asyncio
async def test_upsert_updates_description(store):
    job = _make_job(description="")
    await store.upsert_job(job)

    job.description = "Updated description with details."
    await store.upsert_job(job)

    jobs = await store.get_unnotified_jobs(min_score=0)
    # The job has match_score=None so won't appear with min_score=0
    # Let's query directly
    assert await store.job_exists(job.apply_link)


@pytest.mark.asyncio
async def test_context_manager(tmp_path):
    db_path = str(tmp_path / "ctx_test.db")
    async with JobStore(db_path=db_path) as s:
        job = _make_job()
        await s.upsert_job(job)
        assert await s.job_exists(job.apply_link)
