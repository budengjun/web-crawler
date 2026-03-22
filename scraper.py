import asyncio
import logging
from typing import List, Dict, Any
from playwright.async_api import async_playwright, Page, Response
from playwright_stealth import stealth_async
from models import Job
from datetime import datetime

logger = logging.getLogger(__name__)

class ScraperEngine:
    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.intercepted_data = []

    async def _handle_response(self, response: Response):
        """API Interception: 尝试拦截并保存返回的 JSON 数据"""
        url = response.url
        if ("graphql" in url or "api" in url or "jobs" in url) and response.request.resource_type in ["fetch", "xhr"]:
            try:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    data = await response.json()
                    self.intercepted_data.append({"url": url, "data": data})
                    # 这里可以添加针对 Lever/Greenhouse/Workday API 的特定解析逻辑
            except Exception:
                pass

    async def scrape_target(self, target: Dict[str, Any]) -> List[Job]:
        company_name = target['name']
        url = target['url']
        platform_type = target.get('type', 'custom')
        self.intercepted_data = [] # 每次抓取前重置
        
        logger.info(f"Starting scrape for {company_name} ({platform_type}) at {url}")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            # 自定义 User-Agent 和 浏览器指纹伪装
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=2,
                has_touch=False,
                is_mobile=False
            )
            page = await context.new_page()
            
            # 使用 playwright-stealth 绕过反爬 (Cloudflare 等)
            await stealth_async(page)
            
            # 设置 API Interception
            page.on("response", self._handle_response)

            scraped_jobs = []

            try:
                await page.goto(url, wait_until="networkidle", timeout=self.timeout)
                
                # 检查是否成功拦截到了有用数据，如果拦截到了可以直接解析 JSON，省去 DOM 解析
                # 这里为了演示，我们假设 fallback 到 DOM 解析：
                
                if platform_type == "workday":
                    scraped_jobs = await self._scrape_workday(page, company_name)
                elif platform_type in ["lever", "greenhouse"]:
                    scraped_jobs = await self._scrape_lever_greenhouse(page, company_name)
                else:
                    scraped_jobs = await self._scrape_custom(page, company_name)
                    
            except Exception as e:
                logger.error(f"Failed to scrape {company_name}: {e}")
            finally:
                await browser.close()
                
            return scraped_jobs

    async def _scrape_workday(self, page: Page, company_name: str) -> List[Job]:
        """处理 Workday 类型: 动态加载和嵌套 iframe (或 Load More)"""
        jobs = []
        try:
            # 尝试处理 Infinite Scroll / Load More
            for _ in range(5): 
                try:
                    load_more = page.locator('button[data-automation-id="loadMoreJobs"]')
                    if await load_more.is_visible(timeout=2000):
                        await load_more.click()
                        await page.wait_for_timeout(2000) # 等待数据加载
                    else:
                        break
                except Exception:
                    break
                    
            # 简单的 DOM 解析示例 (需要根据实际页面元素调整)
            # 提示: 实际抓取时，可能需要进入详情页获取 description，这里以占位符代替
            job_elements = await page.locator('li.css-1q2dra3').all() # Example selector for Workday lists
            
            for el in job_elements:
                try:
                    title_el = el.locator('h3 a')
                    title = await title_el.inner_text()
                    link = await title_el.get_attribute('href')
                    full_link = f"https://{page.url.split('/')[2]}{link}" if link and link.startswith('/') else link
                    
                    jobs.append(Job(
                        title=title.strip(),
                        company=company_name,
                        location="Check Listing", # Workday usually has nested locators for location
                        description="Description to be fetched from individual job page or API...",
                        apply_link=full_link or page.url,
                        posted_date=datetime.now() # 占位
                    ))
                except Exception as e:
                    logger.warning(f"Error parsing a Workday job element: {e}")
                    
        except Exception as e:
            logger.error(f"Workday scraping error: {e}")
            
        return jobs

    async def _scrape_lever_greenhouse(self, page: Page, company_name: str) -> List[Job]:
        """处理 Greenhouse/Lever 类型: 结构简单，优先尝试从 DOM 快速抽取"""
        jobs = []
        try:
            # Lever 常见结构: div.posting
            posting_elements = await page.locator('.posting, .level-0').all()
            for posting in posting_elements:
                try:
                    title_el = posting.locator('h5, a')
                    title = await title_el.first.inner_text()
                    link = await title_el.first.get_attribute('href')
                    
                    # 尝试寻找 Location
                    loc_text = "Remote/Vancouver"
                    loc_el = posting.locator('.sort-by-location, .location')
                    if await loc_el.count() > 0:
                        loc_text = await loc_el.first.inner_text()
                    
                    jobs.append(Job(
                        title=title.strip(),
                        company=company_name,
                        location=loc_text.strip(),
                        description="Detail required from job page...",
                        apply_link=link or page.url,
                        posted_date=datetime.now()
                    ))
                except Exception as e:
                     logger.debug(f"Skipping Lever/Greenhouse element: {e}")
        except Exception as e:
             logger.error(f"Lever/Greenhouse scraping error: {e}")
        return jobs

    async def _scrape_custom(self, page: Page, company_name: str) -> List[Job]:
        """Fallback 针对未分类的初创网站"""
        jobs = []
        logger.info(f"Running generic fallback scraper for {company_name}")
        # 可以用更广义的 XPath 或 Locator 寻找带有 'Engineer', 'Developer' 字样的 a 标签
        return jobs
