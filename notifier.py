import asyncio
import aiohttp
import logging
from models import Job
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Delay between consecutive webhook sends to respect Discord rate limits
WEBHOOK_SEND_DELAY_SECONDS = 1.0


class Notifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_notification(
        self,
        jobs: List[Job],
        store=None,
    ):
        """
        Send notifications for qualifying jobs.

        Args:
            jobs: List of evaluated Job objects.
            store: Optional JobStore instance — if provided, only unnotified jobs
                   are sent and then marked as notified.
        """
        if not self.webhook_url or self.webhook_url == "YOUR_DISCORD_OR_TELEGRAM_WEBHOOK_URL":
            logger.warning("Webhook URL not configured. Skipping notifications.")
            return

        now = datetime.now(timezone.utc)
        sent_count = 0

        for job in jobs:
            # ── Recency check ──
            is_recent = True
            if job.posted_date:
                posted_aware = (
                    job.posted_date.replace(tzinfo=timezone.utc)
                    if job.posted_date.tzinfo is None
                    else job.posted_date
                )
                if (now - posted_aware) > timedelta(hours=24):
                    is_recent = False

            # ── Score & dedup check ──
            if job.match_score and job.match_score > 80 and is_recent:
                if job.notified:
                    continue

                success = await self._send_discord_webhook(job)

                if success and store:
                    await store.mark_notified(job.apply_link)

                if success:
                    sent_count += 1

                # Rate-limit: wait between sends
                await asyncio.sleep(WEBHOOK_SEND_DELAY_SECONDS)

        logger.info(f"Sent {sent_count} notifications.")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def _send_discord_webhook(self, job: Job) -> bool:
        """Send a single Discord embed for a job. Returns True on success."""
        # Sanitization: Ensure no fields are empty or just whitespace (Discord 400 requirements)
        title = (job.title or "Unknown Job").strip() or "Unknown Job"
        company = (job.company or "Unknown Company").strip() or "Unknown Company"
        location = (job.location or "N/A").strip() or "N/A"
        reasoning = (job.match_reasoning or "N/A").strip() or "N/A"
        
        # URL Validation
        link = job.apply_link if job.apply_link and job.apply_link.startswith("http") else None
        
        if not link:
            logger.warning(f"Skipping notification for {title} @ {company}: Invalid or missing URL.")
            return False

        payload = {
            "content": f"🚀 **High-Match Job Alert!** ({job.match_score}/100)",
            "embeds": [
                {
                    "title": f"{title} @ {company}",
                    "url": link,
                    "color": 5814783,
                    "fields": [
                        {"name": "Location", "value": location, "inline": True},
                        {"name": "Score", "value": str(job.match_score), "inline": True},
                        {
                            "name": "Reasoning",
                            "value": reasoning[:1024],
                        },
                    ],
                    "footer": {
                        "text": (
                            f"Posted: {job.posted_date.strftime('%Y-%m-%d')}"
                            if job.posted_date
                            else "Posted: Unknown"
                        )
                    },
                }
            ],
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status not in (200, 204):
                        body = await response.text()
                        logger.error(
                            f"Failed to send webhook for {job.title}: {response.status} {body}\n"
                            f"Payload was: {json.dumps(payload, ensure_ascii=False)}"
                        )
                        return False
                    else:
                        logger.info(f"Successfully sent notification for {job.title}")
                        return True
        except Exception as e:
            logger.error(f"Error sending webhook: {e}")
            raise  # Let tenacity retry
