# Permissions and file safety

The agent asks before it does anything risky. File tools can't leave the project folder or touch secrets, and every file it overwrites is backed up first.

## Using it

When the model wants to run a tool that needs approval, a **Permission Required** card shows the action, its risk, the model's reason and the exact arguments (for `edit_file`, the old and new text). **Approve** runs exactly that call and the request continues where it stopped. **Reject** tells the model no, and it chooses something else. In the CLI, the same question is a y/n prompt.

## How it works

- **Risk levels.** Each tool in `tools/registry.py` is `low`, `medium` or `high`. Low-risk tools run without asking; the rest ask.
- **Rules.** `RULES` in `config/settings.py` overrides that per tool: `"ask"` always asks (e.g. `write_file`, `edit_file`, `create_calendar_event`), `"auto"` never asks (e.g. `read_files`, `search_files`).
- **External tools** (web search, news, page reading) send data off the machine. They ask once per login session, then not again until you log out (CLI: once per process). `"auto"` doesn't apply to them.
- **One approval, one call.** A paused request is parked in memory under a single-use id that belongs to your login session (`core/runs.py`). The card sends only that id, so approving can't run anything other than what was shown.
- **Sandbox.** File tools resolve every path inside the project folder, symlinks included (`tools/files.py`). They refuse secrets and credentials: `.env*`, keys and certificates, SSH keys, `.netrc`, `credentials*`, `secrets*`, `.git/`, the event log and the conversation database.
- **Backups.** `write_file`, `edit_file` and `extract_inline_scripts` save the previous version to `local_storage/backups/<timestamp>/<path>` before writing. The tool result names the backup. Nothing prunes old backups yet.

## Settings

| Setting | Where | Purpose |
| --- | --- | --- |
| `RULES` | `config/settings.py` | Per-tool `"ask"` / `"auto"` override |
| `APP_LOGIN_PASSWORD` | `.env` | Web UI login password |
| `SESSION_SECRET` | `.env` | Signs the login cookie (at least 32 characters; the app won't start without it) |

## Limits

- Parked approvals are in-memory, so they're lost when the server restarts.
- There's no diff view on the card; it shows the raw arguments.
