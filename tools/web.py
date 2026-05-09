from datetime import datetime
from duckduckgo_search import DDGS
from config.settings import MAX_RESULTS
import time

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