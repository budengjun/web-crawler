"""Tests for ScraperEngine's _parse_intercepted_data method."""

import pytest
from datetime import datetime, timezone
from scraper import ScraperEngine


class TestParseInterceptedData:
    """Test API interception parsing with various JSON structures."""

    def _engine(self):
        return ScraperEngine(headless=True, timeout=5000)

    def test_lever_style_list(self):
        """Lever returns a flat list of posting objects."""
        engine = self._engine()
        engine.intercepted_data = [
            {
                "url": "https://api.lever.co/v0/postings/acme",
                "data": [
                    {
                        "text": "Senior ML Engineer",
                        "hostedUrl": "https://jobs.lever.co/acme/abc123",
                        "categories": {"location": "Vancouver, BC"},
                        "descriptionPlain": "Build ML systems at scale.",
                        "createdAt": 1700000000000,
                    },
                    {
                        "text": "Frontend Developer",
                        "hostedUrl": "https://jobs.lever.co/acme/def456",
                        "categories": {"location": "Remote"},
                    },
                ],
            }
        ]

        jobs = engine._parse_intercepted_data("Acme Corp")
        assert len(jobs) == 2
        assert jobs[0].title == "Senior ML Engineer"
        assert jobs[0].location == "Vancouver, BC"
        assert jobs[0].description == "Build ML systems at scale."
        assert jobs[0].company == "Acme Corp"
        assert "lever.co" in jobs[0].apply_link
        assert jobs[1].title == "Frontend Developer"

    def test_greenhouse_style_nested(self):
        """Greenhouse wraps jobs in a { "jobs": [...] } object."""
        engine = self._engine()
        engine.intercepted_data = [
            {
                "url": "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
                "data": {
                    "jobs": [
                        {
                            "title": "Data Scientist",
                            "absolute_url": "https://boards.greenhouse.io/acme/jobs/111",
                            "location": {"name": "Toronto, ON"},
                            "updated_at": "2025-01-15T10:00:00Z",
                        }
                    ]
                },
            }
        ]

        jobs = engine._parse_intercepted_data("Acme")
        assert len(jobs) == 1
        assert jobs[0].title == "Data Scientist"
        assert jobs[0].location == "Toronto, ON"
        assert "greenhouse.io" in jobs[0].apply_link

    def test_empty_intercepted_data(self):
        """No intercepted data returns empty list."""
        engine = self._engine()
        engine.intercepted_data = []
        assert engine._parse_intercepted_data("X") == []

    def test_non_job_api_responses_ignored(self):
        """Intercepted data without recognizable job fields is skipped."""
        engine = self._engine()
        engine.intercepted_data = [
            {
                "url": "https://api.example.com/analytics",
                "data": {"page_views": 1234, "sessions": 56},
            }
        ]
        jobs = engine._parse_intercepted_data("Example")
        assert len(jobs) == 0

    def test_mixed_valid_and_invalid_records(self):
        """Parser extracts valid records and skips invalid ones."""
        engine = self._engine()
        engine.intercepted_data = [
            {
                "url": "https://api.example.com/jobs",
                "data": {
                    "results": [
                        {"title": "Valid Job", "url": "https://example.com/j/1"},
                        {"not_a_title": "Missing title field"},
                        "just a string, not a dict",
                    ]
                },
            }
        ]

        jobs = engine._parse_intercepted_data("Example")
        assert len(jobs) == 1
        assert jobs[0].title == "Valid Job"

    def test_unix_timestamp_parsed(self):
        """Unix millisecond timestamps are parsed to datetime."""
        engine = self._engine()
        engine.intercepted_data = [
            {
                "url": "https://api.lever.co/v0/postings/co",
                "data": [
                    {
                        "text": "Engineer",
                        "hostedUrl": "https://example.com",
                        "createdAt": 1700000000000,
                    }
                ],
            }
        ]

        jobs = engine._parse_intercepted_data("Co")
        assert len(jobs) == 1
        assert jobs[0].posted_date is not None
        assert isinstance(jobs[0].posted_date, datetime)
