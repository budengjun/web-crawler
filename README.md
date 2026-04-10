# AI Job Scraper (North America / Vancouver Focus)

A Python + Playwright automated web scraper that monitors tech company career pages for Full-stack and AI/ML positions, scores them using Gemini API, and sends alerts via Webhooks.

## Features
- **Headless Browser**: Uses `playwright` with `playwright-stealth` to bypass basic anti-bot systems.
- **API Interception First**: Intercepts JSON responses from career APIs (Lever, Greenhouse, Workday) and parses job data directly — falls back to DOM parsing only when interception yields nothing.
- **AI Filtering (Gemini)**: Leverages Google Gemini 2.5 Flash to read job descriptions and score matching likelihood for Full-stack/AI profiles. Evaluates jobs concurrently with bounded concurrency.
- **Webhook Alerts**: Sends notifications to Discord or Telegram for high-matching recent jobs, with rate limiting to avoid API throttling.
- **Modular OOP Structure**: Easily extensible for new ATS platforms (Workday, Greenhouse, Lever, Custom) with configurable CSS selectors per target.
- **SQLite Persistence**: Stores all scraped jobs in a local SQLite database for deduplication — previously-seen jobs are skipped, and notifications are never sent twice.
- **Retry / Backoff**: All network operations (scraping, AI evaluation, webhook sends) use exponential backoff with up to 3 retries via `tenacity`.
- **Environment Variable Support**: API keys and webhook URLs can be provided via `config.yaml` or environment variables (`GEMINI_API_KEY`, `WEBHOOK_URL`), making CI/CD deployment seamless.

## Setup Instructions

1. **Install Dependencies**:
```bash
conda create -n web-crawler python=3.11 -y
conda activate web-crawler
pip install -r requirements.txt
playwright install chromium
```

2. **Configuration**:
- Open `config.yaml`
- Replace `YOUR_DISCORD_OR_TELEGRAM_WEBHOOK_URL` with your Discord/Telegram Webhook URL.
- Replace `YOUR_GEMINI_API_KEY` with your Google Gemini API Key.
- (Optional) Modify `targets` to add or remove companies.
- (Optional) Add custom CSS `selectors` to any target for site-specific DOM parsing.

3. **Run Locally**:
```bash
python main.py
```

4. **Run Tests**:
```bash
python -m pytest tests/ -v
```

## Architecture

```
main.py          — orchestrates the scrape → AI filter → notify pipeline
scraper.py       — Playwright-based scraping engine with API interception
ai_filter.py     — Gemini-powered job evaluation with concurrent processing
notifier.py      — Discord webhook notifications with rate limiting
storage.py       — SQLite-backed persistence and deduplication
models.py        — Pydantic Job data model
config.yaml      — targets, keywords, and settings
```

### Pipeline Flow

1. **Scraping** — A single browser instance visits all configured career pages. API responses are intercepted first; DOM parsing is the fallback. Pagination (Load More / infinite scroll) is handled automatically.
2. **Deduplication** — New jobs are inserted into SQLite; previously-seen jobs are skipped from AI evaluation.
3. **AI Evaluation** — New jobs are scored concurrently (up to 5 simultaneous Gemini calls) against your keyword profile.
4. **Notification** — Jobs scoring > 80 that haven't been notified before are sent to Discord with 1-second rate limiting between messages.

## Low-Cost Deployment (GitHub Actions)
You can deploy this for free using GitHub Actions. Create `.github/workflows/scrape.yml` in your repository:

```yaml
name: Daily Job Scraper

on:
  schedule:
    - cron: '0 16 * * *' # Runs every day at 16:00 UTC (9:00 AM PST)
  workflow_dispatch: # Allows manual trigger

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4
        
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          playwright install chromium
          
      - name: Run Scraper
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          WEBHOOK_URL: ${{ secrets.WEBHOOK_URL }}
        run: python main.py
```

> **Note:** API keys are read from environment variables automatically when not set in `config.yaml`, so GitHub Actions secrets work out of the box.
