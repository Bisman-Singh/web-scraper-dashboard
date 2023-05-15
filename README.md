# Web Scraper Dashboard

Scrape top headlines from Hacker News, Reddit Programming, and GitHub Trending, served via a web dashboard.

## Features

- Multi-source scraping (Hacker News, Reddit, GitHub Trending)
- Concurrent scraping with ThreadPoolExecutor
- SQLite storage for scraped headlines
- Beautiful dark-themed web dashboard
- One-click refresh from the UI
- REST API for programmatic access

## Usage

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8002 in your browser.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/headlines` | Get all headlines (?source= to filter) |
| GET | `/api/refresh` | Trigger a fresh scrape |
