"""Tests for AIFilter JSON parsing and evaluation logic."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from models import Job
from ai_filter import AIFilter
from datetime import datetime, timezone

import ai_filter
ai_filter._QUOTA_WAIT_SECONDS = 0

def _make_job(**overrides) -> Job:
    defaults = dict(
        title="ML Engineer",
        company="TestCo",
        location="Vancouver",
        description="Build ML pipelines using PyTorch and LangChain.",
        apply_link="https://testco.com/ml",
        posted_date=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Job(**defaults)


class TestJSONParsing:
    """Test the JSON parsing in evaluate_job with various response formats."""

    @pytest.mark.asyncio
    async def test_clean_json_response(self):
        """Model returns clean JSON without fences."""
        ai = AIFilter(api_key="", keywords=["Python", "PyTorch"])
        ai.client = MagicMock()

        mock_response = MagicMock()
        mock_response.text = '{"score": 85, "reasoning": "Good fit"}'
        ai.client.models.generate_content = AsyncMock(return_value=mock_response)

        job = _make_job()
        result = await ai.evaluate_job(job)
        assert result.match_score == 85
        assert result.match_reasoning == "Good fit"

    @pytest.mark.asyncio
    async def test_fenced_json_response(self):
        """Model returns JSON wrapped in ```json fences."""
        ai = AIFilter(api_key="", keywords=["Python"])
        ai.client = MagicMock()

        mock_response = MagicMock()
        mock_response.text = '```json\n{"score": 72, "reasoning": "Partial match"}\n```'
        ai.client.models.generate_content = AsyncMock(return_value=mock_response)

        job = _make_job()
        result = await ai.evaluate_job(job)
        assert result.match_score == 72

    @pytest.mark.asyncio
    async def test_plain_fenced_response(self):
        """Model returns JSON wrapped in plain ``` fences."""
        ai = AIFilter(api_key="", keywords=["Python"])
        ai.client = MagicMock()

        mock_response = MagicMock()
        mock_response.text = '```\n{"score": 60, "reasoning": "Weak match"}\n```'
        ai.client.models.generate_content = AsyncMock(return_value=mock_response)

        job = _make_job()
        result = await ai.evaluate_job(job)
        assert result.match_score == 60

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_zero(self):
        """When no API key is set, score defaults to 0."""
        ai = AIFilter(api_key="", keywords=["Python"])
        # client should be None
        assert ai.client is None

        job = _make_job()
        result = await ai.evaluate_job(job)
        assert result.match_score == 0
        assert "disabled" in result.match_reasoning.lower()


class TestConcurrentEvaluation:
    """Test the batch evaluate_jobs method."""

    @pytest.mark.asyncio
    async def test_evaluate_jobs_no_api_key(self):
        """Without API key, all jobs get score 0."""
        ai = AIFilter(api_key="", keywords=["Python"])
        jobs = [_make_job(apply_link=f"https://a.com/{i}") for i in range(3)]

        results = await ai.evaluate_jobs(jobs)
        assert len(results) == 3
        assert all(j.match_score == 0 for j in results)

    @pytest.mark.asyncio
    async def test_evaluate_jobs_concurrent(self):
        """Concurrent evaluation processes all jobs."""
        ai = AIFilter(api_key="", keywords=["Python"])
        ai.client = MagicMock()

        mock_response = MagicMock()
        mock_response.text = '{"score": 80, "reasoning": "Match"}'
        ai.client.models.generate_content = AsyncMock(return_value=mock_response)

        jobs = [_make_job(apply_link=f"https://a.com/{i}") for i in range(5)]
        results = await ai.evaluate_jobs(jobs)

        assert len(results) == 5
        assert all(j.match_score == 80 for j in results)
