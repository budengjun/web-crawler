"""Tests for Notifier filtering logic and timezone handling."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from models import Job
from notifier import Notifier


def _make_job(**overrides) -> Job:
    defaults = dict(
        title="Engineer",
        company="TestCo",
        location="Vancouver",
        description="Build things.",
        apply_link="https://testco.com/jobs/1",
        posted_date=datetime.now(timezone.utc),
        match_score=90,
        match_reasoning="Great fit",
    )
    defaults.update(overrides)
    return Job(**defaults)


class TestFilteringLogic:
    """Test which jobs are selected for notification."""

    @pytest.mark.asyncio
    async def test_high_score_recent_job_is_sent(self):
        """Jobs with score > 80 and posted within 24h should be sent."""
        notifier = Notifier(webhook_url="https://discord.com/api/webhooks/fake")

        with patch.object(notifier, "_send_discord_webhook", new_callable=AsyncMock, return_value=True) as mock_send:
            job = _make_job(match_score=90, posted_date=datetime.now(timezone.utc))
            await notifier.send_notification([job])
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_low_score_job_is_not_sent(self):
        """Jobs with score <= 80 should be skipped."""
        notifier = Notifier(webhook_url="https://discord.com/api/webhooks/fake")

        with patch.object(notifier, "_send_discord_webhook", new_callable=AsyncMock) as mock_send:
            job = _make_job(match_score=50)
            await notifier.send_notification([job])
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_old_job_is_not_sent(self):
        """Jobs posted more than 24 hours ago should be skipped."""
        notifier = Notifier(webhook_url="https://discord.com/api/webhooks/fake")

        with patch.object(notifier, "_send_discord_webhook", new_callable=AsyncMock) as mock_send:
            old_date = datetime.now(timezone.utc) - timedelta(hours=48)
            job = _make_job(match_score=95, posted_date=old_date)
            await notifier.send_notification([job])
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_already_notified_job_is_skipped(self):
        """Jobs marked as notified should not be sent again."""
        notifier = Notifier(webhook_url="https://discord.com/api/webhooks/fake")

        with patch.object(notifier, "_send_discord_webhook", new_callable=AsyncMock) as mock_send:
            job = _make_job(match_score=95, notified=True)
            await notifier.send_notification([job])
            mock_send.assert_not_called()


class TestTimezoneHandling:
    """Verify that timezone-aware and naive datetimes are handled correctly."""

    @pytest.mark.asyncio
    async def test_naive_datetime_treated_as_utc(self):
        """A timezone-naive posted_date should be treated as UTC and still qualify."""
        notifier = Notifier(webhook_url="https://discord.com/api/webhooks/fake")

        with patch.object(notifier, "_send_discord_webhook", new_callable=AsyncMock, return_value=True) as mock_send:
            # Naive datetime (no tzinfo) — should be treated as UTC
            naive_recent = datetime.utcnow()
            job = _make_job(match_score=95, posted_date=naive_recent)
            await notifier.send_notification([job])
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_webhook_url_skips(self):
        """If webhook URL is not configured, no sends happen."""
        notifier = Notifier(webhook_url="YOUR_DISCORD_OR_TELEGRAM_WEBHOOK_URL")
        job = _make_job(match_score=95)
        # Should return without error
        await notifier.send_notification([job])


class TestStoreIntegration:
    """Test that the notifier integrates with JobStore correctly."""

    @pytest.mark.asyncio
    async def test_mark_notified_called_on_success(self):
        """After successful send, store.mark_notified should be called."""
        notifier = Notifier(webhook_url="https://discord.com/api/webhooks/fake")
        mock_store = MagicMock()
        mock_store.mark_notified = AsyncMock()

        with patch.object(notifier, "_send_discord_webhook", new_callable=AsyncMock, return_value=True):
            job = _make_job(match_score=95)
            await notifier.send_notification([job], store=mock_store)
            mock_store.mark_notified.assert_called_once_with(job.apply_link)
