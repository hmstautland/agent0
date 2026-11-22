# Decision log

Important decisions about agent0. Each entry records a choice where several options were viable and each had pros and cons. Small or cosmetic choices (colors, names, wording, formatting) don't go here, and neither do choices with only one sensible answer.

When a later decision replaces an earlier one, add a new entry and change the old entry's status to `Superseded by <date>: <title>`. Don't delete old entries.

Entry format:

```
## YYYY-MM-DD: Short title of the decision

**Status:** Accepted

**Context:** Why a decision was needed.

**Options considered:**
- **Option A**: pros / cons
- **Option B**: pros / cons

**Decision:** The option chosen, and the main reason.

**Consequences:** What follows from it, and what would make us revisit it.
```

<!-- New decisions go directly below this line, newest first. -->

## 2026-11-22: One flag per API endpoint instead of one for the whole API

**Status:** Accepted

**Context:** The Kush app's API had two endpoints (explain, lookup) behind a single `trading-signals` flag. Lookup answers arbitrary questions and sends the caller's portfolio to the model, so it can reasonably be switched off while explain stays on, and the other way round.

**Options considered:**
- **One flag for the whole router**: one switch, and a new endpoint is automatically gated / all or nothing, and no way to enable only explain.
- **One flag per endpoint**: finer control over what an outside app can reach, each with its own card and explanation on Config / every new endpoint needs its own flag, and forgetting one would leave it open.

**Decision:** One flag per endpoint (`trading-signals-explain`, `trading-signals-lookup`), set in each endpoint's `route.py`. A test hits every published `/api/v1` route with a valid key and all flags off and expects 403, so a new endpoint without a flag fails the suite. The old combined flag is not migrated; both new flags start off.

**Consequences:** Adding an endpoint means adding a flag constant and a Config card. Revisit if the number of endpoints makes the Config page unwieldy (group them under one card then).

## 2026-11-22: Integration API and feature flags for the Kush app

**Status:** Accepted

**Context:** The Kush trading-signal app should call agent0 to explain signals and to power a lookup search bar. agent0's routes are all session-cookie based, and every 401 redirects to `/login`.

**Options considered:**
- **Reuse the login session**: no new auth code / an outside app would need to log in with the human password and keep a cookie.
- **Separate Bearer-key API**: one key, real 401s, easy for server-to-server calls / a new setting (`AGENT_API_KEY`) and a router to maintain.
- **Run lookup through the agent loop with read-only tools or web search**: can fetch live data / needs permission grants (external tools always ask) and widens what an outside caller can make agent0 do.
- **Model-only endpoints**: one `chat()` call with its own prompt, no tools, no grants, no memory / answers can be out of date, and portfolio data must be sent by the caller.
- **A separate small model setting for the API**: faster explain calls / an extra setting and a second model to load, so Ollama reloads when switching.

**Decision:** A separate Bearer-key API (`features/api/`) whose two endpoints are model-only: no agent0 tools (web search included), no permission grants hard-coded or sent by the caller, and no new model setting (both use `OLLAMA_MODEL`). The whole router sits behind an on/off flag stored in SQLite and switched on the new Config page; every integration is off by default, and the key is checked before the flag so callers learn nothing about it.

**Consequences:** An outside app can never trigger a tool or an approval in agent0, and switching it off cuts it off immediately. Revisit if lookup needs live data (that needs a deliberate, separate grant design) or if explain latency on the 35B model becomes a problem (then a per-endpoint model setting).
