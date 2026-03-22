import aiohttp
import logging
from models import Job
from typing import List
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

class Notifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_notification(self, jobs: List[Job]):
        if not self.webhook_url or self.webhook_url == "YOUR_DISCORD_OR_TELEGRAM_WEBHOOK_URL":
            logger.warning("Webhook URL not configured. Skipping notifications.")
            return

        now = datetime.now(timezone.utc)
        for job in jobs:
            # 判断: 匹配度 > 80 且是 24 小时内发布的新职位
            # (如果爬取不到 posted_date，可默认当做新职位发送)
            is_recent = True
            if job.posted_date:
                # Assuming job.posted_date is timezone aware or naive localized
                time_diff = now - job.posted_date.replace(tzinfo=timezone.utc) if job.posted_date.tzinfo is None else now - job.posted_date
                if time_diff > timedelta(hours=24):
                    is_recent = False

            if job.match_score and job.match_score > 80 and is_recent:
                await self._send_discord_webhook(job)
                
    async def _send_discord_webhook(self, job: Job):
        payload = {
            "content": f"🚀 **高匹配度岗位提醒!** ({job.match_score}/100)",
            "embeds": [
                {
                    "title": f"{job.title} @ {job.company}",
                    "url": job.apply_link,
                    "color": 5814783,
                    "fields": [
                        {"name": "Location", "value": job.location, "inline": True},
                        {"name": "Score", "value": str(job.match_score), "inline": True},
                        {"name": "Reasoning", "value": job.match_reasoning[:1024]} # Discord limits field value to 1024 chars
                    ],
                    "footer": {
                        "text": f"Posted: {job.posted_date.strftime('%Y-%m-%d') if job.posted_date else 'Unknown'}"
                    }
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status not in (200, 204):
                        logger.error(f"Failed to send webhook for {job.title}: {response.status} {await response.text()}")
                    else:
                        logger.info(f"Successfully sent notification for {job.title}")
        except Exception as e:
            logger.error(f"Error sending webhook: {e}")
