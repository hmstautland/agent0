# Web search

The agent can search the web, fetch news headlines and read pages.

## Using it

Ask something that needs current information, e.g. "What is in the news in Brazil?" or "Search for the Ollama release notes and summarise them". The first web tool call each login session shows a permission card (see [permissions](permissions.md)).

## How it works

Code: `tools/web.py`.

| Tool | What it does |
| --- | --- |
| `search_web` | DuckDuckGo search (`ddgs`), returning title, URL and snippet for each result |
| `get_news` | A news search limited to Reuters, BBC, AP, NRK and VG for the current year |
| `read_web_content` | Fetches pages and strips them to plain text (first 20,000 characters each) |

All three are marked `external`: they ask once per login session.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `MAX_RESULTS` (`config/settings.py`) | `5` | Search results per query |

## Limits

- Each tool can be called at most once every 5 seconds. Faster calls return "Rate limit exceeded".
- The page fetch is plain HTTP, so there's no JavaScript rendering, clicking or logging in.
