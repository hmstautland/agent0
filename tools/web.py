from datetime import datetime
from ddgs import DDGS
from config.settings import MAX_RESULTS
import time
import requests
import re


def _extract_text_from_html(html):
    # remove script/style
    html = re.sub(r"<script.*?>.*?</script>", "", html, flags=re.S|re.I)
    html = re.sub(r"<style.*?>.*?</style>", "", html, flags=re.S|re.I)
    # remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    # collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def read_web_content(urls):
    """Fetch and return textual content for a list of URLs."""
    if not rate_limit("read_web_content"):
        return "Rate limit exceeded"

    if not isinstance(urls, (list, tuple)):
        return "urls must be a list"

    results = {}
    for url in urls:
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                results[url] = f"HTTP {r.status_code}"
                continue

            text = _extract_text_from_html(r.text)
            # limit size
            results[url] = text[:20000]
        except Exception as e:
            results[url] = str(e)

    return results

def search_web(query):
    if not rate_limit("search_web"):
        return "Rate limit exceeded"
    results = []

    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=MAX_RESULTS):
            results.append({
                "title": r["title"],
                "url": r["href"],
                "snippet": r["body"],
                "source": "duckduckgo-search"
            })
    return results

def get_news(country):
    if not rate_limit("get_news"):
        return "Rate limit exceeded"

    query = f"latest news {country} site:reuters.com OR site:bbc.com OR site:apnews.com OR site:nrk.no OR site:vg.no {datetime.now().year}"
    return search_web(query);


last_called = {};
COOL_DOWN = 5;

def rate_limit(tool_name, cooldown=COOL_DOWN):
    now = time.time()
    if tool_name in last_called:
        if now - last_called[tool_name] < cooldown:
            return False
    last_called[tool_name] = now
    return True;