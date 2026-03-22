# AI Job Scraper (North America / Vancouver Focus)

A Python + Playwright automated web scraper that monitors tech company career pages for Full-stack and AI/ML positions, scores them using Gemini API, and sends alerts via Webhooks.

## Features
- **Headless Browser**: Uses `playwright` with `playwright-stealth` to bypass basic anti-bot systems.
- **API Interception First**: Tries to intercept JSON responses containing job data before falling back to DOM parsing.
- **AI Filtering (Gemini)**: Leverages Google Gemini 2.5 Flash to read job descriptions and score matching likelihood for Full-stack/AI profiles.
- **Webhook Alerts**: Sends notifications to Discord or Telegram for high-matching recent jobs.
- **Modular OOP Structure**: Easily extensible for new ATS platforms (Workday, Greenhouse, Lever, Custom).

## Setup Instructions

1. **Install Dependencies**:
```bash
conda create -n web-crawler-env python=3.11 -y
conda activate web-crawler-env
pip install -r requirements.txt
playwright install chromium
```

2. **Configuration**:
- Open `config.yaml`
- Replace `YOUR_DISCORD_OR_TELEGRAM_WEBHOOK_URL` with your Discord/Telegram Webhook URL.
- Replace `YOUR_GEMINI_API_KEY` with your Google Gemini API Key.
- (Optional) Modify `targets` to add or remove companies.

3. **Run Locally**:
```bash
python main.py
```

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
*Note: You would need to update `main.py` to optionally read API keys from environment variables (`os.environ`) for the Actions setup.*
