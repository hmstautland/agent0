# Config

A dashboard for switching integrations on and off, like a feature-flag page.

## Using it

After logging in, click **Config** (white underlined link, top-left of the chat page). Each integration (for the API, each endpoint) is one card with an explanation, its endpoints, whether `AGENT_API_KEY` is set, an on/off switch, and a **Decisions** list with the design decisions behind it (also in the [decision log](../DECISIONS.md)). Everything is **off** until you switch it on, and an app that is switched off cannot reach agent0 at all.

Today there are two, one per endpoint of the [HTTP API](api.md): *Trading signals (Kush app): Explain* and *Lookup*.

## How it works

`features/config/` has the page (`GET /config`) and the switch (`POST /config/integrations/<key>`), both behind login. The flags are rows in the `integration_flags` table (`storage/integrations.py`); a missing row means off. The list of integrations, with their descriptions, is `features/config/integrations.py`: adding an integration is adding an entry there and checking `storage.integrations.is_enabled(key)` in its routes.

## Limits

- The page never shows the API key, only whether it is set. The key itself lives in `.env`.
