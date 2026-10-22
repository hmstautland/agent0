"""Keeps the tool loop's message history inside the model's context window.

Ollama silently drops whatever overflows num_ctx, so the loop trims on its
own terms instead: one oversized tool result is cut down when it is added
(cap_result), and older tool results are swapped for a short stub before each
model call (prune_messages). Both are plain string handling - no extra model
call - and the stub says the result can be fetched again.
"""

import re

from core.llm import OLLAMA_CODE_NUM_CTX

# Share of the window the history may use; the rest is for the tool schemas
# and the model's reply.
BUDGET_RATIO = 0.75
CONTEXT_BUDGET_TOKENS = int(OLLAMA_CODE_NUM_CTX * BUDGET_RATIO)

# Newest tool results always kept whole - the model is usually still working
# from them (an edit needs the exact text of the file it just read).
KEEP_RECENT_RESULTS = 2

# One result may take at most about half the budget (~4 chars per token), so a
# multi-file read still fits whole while one runaway result can't fill the window.
MAX_RESULT_CHARS = CONTEXT_BUDGET_TOKENS * 2

STUB_PREVIEW_CHARS = 80

_RANGE_HEADER_RE = re.compile(r"\[lines (\d+)-\d+ of \d+\]\n")


def estimate_tokens(messages):
    """Rough token count (about 4 characters per token) over content and tool-call arguments."""
    chars = 0
    for message in messages:
        chars += len(str(message.get("content") or ""))
        for call in message.get("tool_calls") or []:
            chars += len(str(call))
    return chars // 4


def cap_result(text, limit=MAX_RESULT_CHARS, tool=None):
    """Keep the start and end of an oversized result, with a marker for what was cut.

    For read_files the marker gives the omitted line range, so the model can
    ask for exactly that section with start_line/end_line.
    """
    if len(text) <= limit:
        return text
    head, tail = limit * 2 // 3, limit // 3
    omitted = len(text) - head - tail
    first = text.count("\n", 0, head) + 1
    last = text.count("\n", 0, len(text) - tail) + 1
    if tool == "read_files":
        # A ranged read starts with a "[lines a-b of N]" header line, so line k
        # of the text is line a + k - 2 of the file (line 1 is the header).
        ranged = _RANGE_HEADER_RE.match(text)
        if ranged:
            offset = int(ranged.group(1)) - 2
            first, last = max(first + offset, 1), max(last + offset, 1)
    if tool == "read_files":
        advice = f"Call read_files again with start_line={first} and end_line={last} (or a narrower range) to see them"
    else:
        advice = "Call the tool again for the specific section you need"
    return f"{text[:head]}\n[... lines {first}-{last} omitted ({omitted:,} characters) to save context. {advice} ...]\n{text[-tail:]}"


def cap_each(result, tool=None, limit=MAX_RESULT_CHARS, floor=4000):
    """Cap a {path: text} result (several files in one call) per file, so each file keeps its own start and end."""
    if isinstance(result, dict) and result and all(isinstance(v, str) for v in result.values()):
        share = max(limit // len(result), floor)
        return {key: cap_result(value, share, tool) for key, value in result.items()}
    return result


def _stub(message):
    content = str(message.get("content") or "")
    # repr, not a whitespace-collapsed preview: a model that edits from the
    # preview would otherwise reproduce (and silently change) the spacing.
    return (
        f"[earlier {message.get('tool_name', 'tool')} result trimmed to save context, "
        f"{len(content):,} characters, starting: {content[:STUB_PREVIEW_CHARS]!r}. "
        f"Call the tool again for the exact text before editing.]"
    )


def prune_messages(messages, budget=CONTEXT_BUDGET_TOKENS, keep_recent=KEEP_RECENT_RESULTS):
    """Return the history to send to the model, trimmed to the budget; `messages` itself is not changed.

    Oldest tool results are stubbed first until the estimate fits. System,
    user and assistant messages and the newest `keep_recent` tool results are
    never touched.
    """
    if estimate_tokens(messages) <= budget:
        return messages

    tool_indexes = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    trimmable = tool_indexes[:-keep_recent] if keep_recent else tool_indexes

    pruned = list(messages)
    for i in trimmable:
        if estimate_tokens(pruned) <= budget:
            break
        pruned[i] = {**messages[i], "content": _stub(messages[i])}
    return pruned
