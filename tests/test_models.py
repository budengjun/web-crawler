"""Tests for the Job Pydantic model."""

from datetime import datetime, timezone
from models import Job


def test_job_required_fields():
    """Job can be created with only required fields; optionals default correctly."""
    job = Job(
        title="Software Engineer",
        company="Acme Corp",
        location="Vancouver, BC",
        description="Build stuff.",
        apply_link="https://acme.com/jobs/1",
    )
    assert job.title == "Software Engineer"
    assert job.match_score is None
    assert job.match_reasoning is None
    assert job.first_seen is None
    assert job.notified is False


def test_job_with_ai_fields():
    """AI-related optional fields populate correctly."""
    job = Job(
        title="ML Engineer",
        company="BigCo",
        location="Remote",
        description="Train models.",
        apply_link="https://bigco.com/ml",
        match_score=92,
        match_reasoning="Strong LLM alignment",
    )
    assert job.match_score == 92
    assert "LLM" in job.match_reasoning


def test_job_with_persistence_fields():
    """Persistence tracking fields work correctly."""
    now = datetime.now(timezone.utc)
    job = Job(
        title="Data Scientist",
        company="DataCo",
        location="Toronto",
        description="Analyze data.",
        apply_link="https://dataco.com/ds",
        first_seen=now,
        notified=True,
    )
    assert job.first_seen == now
    assert job.notified is True


def test_job_serialization_roundtrip():
    """Job can round-trip through dict serialization."""
    job = Job(
        title="Frontend Dev",
        company="UICo",
        location="Montreal",
        description="React and stuff.",
        apply_link="https://uico.com/fe",
        posted_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
        match_score=75,
    )
    data = job.model_dump()
    restored = Job(**data)
    assert restored.title == job.title
    assert restored.posted_date == job.posted_date
    assert restored.match_score == 75
