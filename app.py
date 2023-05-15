#!/usr/bin/env python3
"""Scrape top news headlines from multiple sources and serve via a web dashboard."""

import sqlite3
import time
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

DB_PATH = Path(__file__).parent / "headlines.db"

app = FastAPI(title="News Scraper Dashboard", version="1.0.0")

SOURCES = {
    "Hacker News": {
        "url": "https://news.ycombinator.com",
        "selector": ".titleline > a",
        "base_url": "https://news.ycombinator.com/",
    },
    "Reddit Programming": {
        "url": "https://old.reddit.com/r/programming/.json",
        "type": "json",
    },
    "GitHub Trending": {
        "url": "https://github.com/trending",
        "selector": "h2.h3 a",
        "base_url": "https://github.com",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS headlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                scraped_at TEXT NOT NULL
            )
        """)


def scrape_html_source(name: str, config: dict) -> list[dict]:
    try:
        resp = requests.get(config["url"], headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []
        for tag in soup.select(config["selector"])[:20]:
            title = tag.get_text(strip=True)
            href = tag.get("href", "")
            if href and not href.startswith("http"):
                href = config.get("base_url", "") + href
            if title:
                items.append({"source": name, "title": title, "url": href})
        return items
    except Exception as e:
        print(f"  Error scraping {name}: {e}")
        return []


def scrape_reddit_json(name: str, config: dict) -> list[dict]:
    try:
        resp = requests.get(config["url"], headers={**HEADERS, "Accept": "application/json"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = []
        for post in data.get("data", {}).get("children", [])[:20]:
            d = post.get("data", {})
            title = d.get("title", "")
            url = d.get("url", "")
            if title:
                items.append({"source": name, "title": title, "url": url})
        return items
    except Exception as e:
        print(f"  Error scraping {name}: {e}")
        return []


def scrape_all() -> list[dict]:
    all_items = []

    def scrape_source(name, config):
        if config.get("type") == "json":
            return scrape_reddit_json(name, config)
        return scrape_html_source(name, config)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(scrape_source, n, c): n for n, c in SOURCES.items()}
        for future in futures:
            all_items.extend(future.result())

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("DELETE FROM headlines")
        for item in all_items:
            conn.execute(
                "INSERT INTO headlines (source, title, url, scraped_at) VALUES (?, ?, ?, ?)",
                (item["source"], item["title"], item["url"], now),
            )
    return all_items


@app.on_event("startup")
def startup():
    init_db()
    scrape_all()


@app.get("/", response_class=HTMLResponse)
def dashboard():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM headlines ORDER BY source, id").fetchall()

    sources = {}
    for row in rows:
        src = row["source"]
        if src not in sources:
            sources[src] = []
        sources[src].append(dict(row))

    source_html = ""
    colors = {"Hacker News": "#ff6600", "Reddit Programming": "#ff4500", "GitHub Trending": "#238636"}
    for source, items in sources.items():
        color = colors.get(source, "#666")
        items_html = "".join(
            f'<li><a href="{it["url"]}" target="_blank">{it["title"]}</a></li>'
            for it in items
        )
        source_html += f"""
        <div class="source-card">
            <h2 style="color:{color}">{source} <span class="count">{len(items)}</span></h2>
            <ul>{items_html}</ul>
        </div>"""

    scraped_at = rows[0]["scraped_at"] if rows else "Never"

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>News Dashboard</title>
<style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family:-apple-system,sans-serif; background:#0a0a0a; color:#e0e0e0; padding:40px 20px; }}
    .header {{ text-align:center; margin-bottom:40px; }}
    .header h1 {{ font-size:2.5rem; color:#fff; }}
    .header p {{ color:#666; margin-top:8px; }}
    .header button {{
        margin-top:15px; padding:10px 25px; background:#1a73e8; color:#fff;
        border:none; border-radius:8px; cursor:pointer; font-size:1rem;
    }}
    .header button:hover {{ background:#1557b0; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(400px,1fr)); gap:25px; max-width:1400px; margin:0 auto; }}
    .source-card {{ background:#111; border-radius:12px; padding:25px; border:1px solid #222; }}
    .source-card h2 {{ font-size:1.3rem; margin-bottom:15px; display:flex; align-items:center; gap:10px; }}
    .count {{ background:#222; padding:2px 10px; border-radius:12px; font-size:0.8rem; color:#888; }}
    ul {{ list-style:none; }}
    li {{ padding:8px 0; border-bottom:1px solid #1a1a1a; }}
    li:last-child {{ border:none; }}
    a {{ color:#8ab4f8; text-decoration:none; line-height:1.4; }}
    a:hover {{ color:#fff; }}
</style></head>
<body>
    <div class="header">
        <h1>News Scraper Dashboard</h1>
        <p>Last scraped: {scraped_at}</p>
        <button onclick="fetch('/api/refresh').then(()=>location.reload())">Refresh Headlines</button>
    </div>
    <div class="grid">{source_html}</div>
</body></html>"""


@app.get("/api/headlines")
def get_headlines(source: str | None = None):
    with get_db() as conn:
        if source:
            rows = conn.execute("SELECT * FROM headlines WHERE source = ?", (source,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM headlines ORDER BY source").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/refresh")
def refresh():
    items = scrape_all()
    return {"message": f"Scraped {len(items)} headlines"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8002, reload=True)
