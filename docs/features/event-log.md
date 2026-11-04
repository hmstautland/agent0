# Event log

Everything the agent does (requests, model calls, tool calls and their results, approvals) is written to `local_storage/logs.txt`, one JSON object per line.

## Using it

The file is too big to open whole, so use `tail` or `grep`:

```
tail -n 50 local_storage/logs.txt
grep '"edit_file"' local_storage/logs.txt | tail
python -m core.logger        # drop entries older than 14 days now
```

## How it works

`core/logger.py`. The CLI and the web server can write to the same file at once, so every write holds a lock file (`logs.txt.lock`). When the log grows past 1 MB, entries older than 14 days are dropped. If it's still over 500 KB after that, the oldest remaining entries go too. A stopped request's lines are removed.

## Limits

- Tool results are logged only in part (the start of each).
- The agent can't read the log; file tools refuse it.
