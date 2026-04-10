import asyncio
import os
import yaml
import logging
from scraper import ScraperEngine
from ml_scorer import MLScorer
from notifier import Notifier
from storage import JobStore

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _resolve_setting(config_value: str, env_var: str, placeholder: str) -> str:
    """Return config_value unless it is empty or a placeholder, then fall back to env var."""
    if config_value and config_value != placeholder:
        return config_value
    return os.environ.get(env_var, "")


async def main():
    # 读取配置文件
    try:
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config.yaml not found. Please ensure it exists in the root directory.")
        return

    settings = config.get('settings', {})
    targets = config.get('targets', [])
    keywords = config.get('keywords', [])

    # Resolve API keys with env-var fallback (useful for CI / GitHub Actions)
    gemini_key = _resolve_setting(
        settings.get('gemini_api_key', ''),
        'GEMINI_API_KEY',
        'YOUR_GEMINI_API_KEY',
    )
    webhook_url = _resolve_setting(
        settings.get('notification_webhook_url', ''),
        'WEBHOOK_URL',
        'YOUR_DISCORD_OR_TELEGRAM_WEBHOOK_URL',
    )

    # Initialize modules
    scraper = ScraperEngine(
        headless=settings.get('headless', True),
        timeout=settings.get('timeout_ms', 30000),
        proxy=settings.get('proxy', None),
    )

    scorer = MLScorer()

    notifier = Notifier(webhook_url=webhook_url)

    async with JobStore() as store:
        # ── Phase 1: Scraping (single shared browser) ──
        all_jobs = await scraper.scrape_all(targets)
        logger.info(f"Total raw jobs scraped: {len(all_jobs)}")

        # ── Phase 1.5: Deduplication ──
        new_jobs = []
        for job in all_jobs:
            is_new = await store.upsert_job(job)
            if is_new:
                new_jobs.append(job)

        logger.info(
            f"New jobs after deduplication: {len(new_jobs)} "
            f"(skipped {len(all_jobs) - len(new_jobs)} already-seen)"
        )

        # ── Phase 1.6: Exclude unwanted seniority levels ──
        TITLE_BLACKLIST = ["senior", "staff", "principal", "lead", "director", "manager"]
        filtered_jobs = []
        excluded = 0
        for job in new_jobs:
            title_lower = job.title.lower()
            if any(word in title_lower for word in TITLE_BLACKLIST):
                excluded += 1
                logger.debug(f"Excluded by title blacklist: {job.title}")
                continue
            filtered_jobs.append(job)

        if excluded:
            logger.info(f"Excluded {excluded} jobs by title blacklist (senior/staff/etc.)")
        new_jobs = filtered_jobs

        if not new_jobs:
            logger.info("No new jobs to evaluate. Done.")
            return

        # ── Phase 2: ML Scoring (instant, no API calls) ──
        logger.info(f"Scoring {len(new_jobs)} new jobs with ML model...")
        evaluated_jobs = scorer.score_jobs(new_jobs)

        # Persist AI scores
        for job in evaluated_jobs:
            await store.upsert_job(job)

        # ── Phase 3: Notification (with dedup & rate limiting) ──
        logger.info("Sending notifications for matched jobs...")
        await notifier.send_notification(evaluated_jobs, store=store)

    logger.info("🚀 Scraping cycle completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
