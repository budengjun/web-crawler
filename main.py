import asyncio
import yaml
import logging
from scraper import ScraperEngine
from ai_filter import AIFilter
from notifier import Notifier

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

    # 初始化各个模块
    scraper = ScraperEngine(
        headless=settings.get('headless', True),
        timeout=settings.get('timeout_ms', 30000)
    )
    
    ai_filter = AIFilter(
        api_key=settings.get('gemini_api_key', ''),
        keywords=keywords
    )
    
    notifier = Notifier(
        webhook_url=settings.get('notification_webhook_url', '')
    )

    all_jobs = []

    # 1. 抓取招聘信息 (Scraping Phase)
    for target in targets:
        jobs = await scraper.scrape_target(target)
        logger.info(f"✅ Found {len(jobs)} jobs for {target['name']}")
        all_jobs.extend(jobs)

    # 2. AI 过滤与打分 (AI Filtering Phase)
    filtered_jobs = []
    logger.info(f"Starting AI Evaluation for {len(all_jobs)} jobs...")
    for job in all_jobs:
        # 为防止并发请求过多导致 Rate Limit，可以根据需要改写为 asyncio.gather(限制并发数)
        evaluated_job = await ai_filter.evaluate_job(job)
        filtered_jobs.append(evaluated_job)

    # 3. 结果通知 (Notification Phase)
    logger.info("Sending notifications for matched jobs...")
    await notifier.send_notification(filtered_jobs)
    
    logger.info("🚀 Scraping cycle completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
