import core.context as ctx


def tool(name, text):
    return {"role": "tool", "tool_name": name, "content": text}


def history(*results):
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "go"}]
    for name, text in results:
        messages.append({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": {}}}]})
        messages.append(tool(name, text))
    return messages


def test_history_under_budget_is_returned_unchanged():
    messages = history(("read_file", "small"))
    assert ctx.prune_messages(messages, budget=1000) is messages


def test_oldest_tool_results_are_stubbed_until_it_fits_and_the_newest_stay_whole():
    messages = history(("read_file", "A" * 4000), ("read_file", "B" * 4000), ("read_file", "C" * 4000), ("read_file", "D" * 4000))

    pruned = ctx.prune_messages(messages, budget=2500, keep_recent=2)

    results = [m["content"] for m in pruned if m["role"] == "tool"]
    assert results[0].startswith("[earlier read_file result trimmed") and "4,000 characters" in results[0]
    assert "Call the tool again" in results[0]
    assert results[2] == "C" * 4000 and results[3] == "D" * 4000


def test_pruning_stops_as_soon_as_the_estimate_fits():
    messages = history(("read_file", "A" * 4000), ("read_file", "B" * 4000), ("read_file", "C" * 100), ("read_file", "D" * 100))

    results = [m["content"] for m in ctx.prune_messages(messages, budget=1500, keep_recent=2) if m["role"] == "tool"]

    assert results[0].startswith("[earlier") and results[1] == "B" * 4000


def test_pruning_does_not_change_the_original_or_touch_other_roles():
    messages = history(("read_file", "A" * 4000), ("read_file", "B" * 4000), ("read_file", "C" * 4000))
    before = [dict(m) for m in messages]

    pruned = ctx.prune_messages(messages, budget=100, keep_recent=1)

    assert messages == before
    assert [m for m in pruned if m["role"] != "tool"] == [m for m in messages if m["role"] != "tool"]


def test_cap_result_keeps_head_and_tail_of_an_oversized_result():
    text = "H" * 600 + "M" * 5000 + "T" * 300

    capped = ctx.cap_result(text, limit=900)

    assert capped.startswith("H" * 600) and capped.endswith("T" * 300)
    assert "to save context" in capped and "omitted (" in capped and len(capped) < len(text)
    assert ctx.cap_result("short", limit=900) == "short"


def test_stub_preview_keeps_the_original_spacing_so_edits_do_not_alter_it():
    messages = history(("read_file", "timeout = 37  # seconds\nverbose = false\n" + "x" * 4000), ("read_file", "B" * 10), ("read_file", "C" * 10))

    stub = ctx.prune_messages(messages, budget=100, keep_recent=2)[3]["content"]

    assert "timeout = 37  # seconds\\nverbose" in stub


def numbered(n):
    return "".join(f"line {i}\n" for i in range(1, n + 1))


def test_read_files_marker_names_the_omitted_line_range():
    capped = ctx.cap_result(numbered(500), limit=900, tool="read_files")

    assert "Call read_files again with start_line=" in capped and "end_line=" in capped


def test_other_tools_get_a_generic_marker():
    assert "read_files" not in ctx.cap_result(numbered(500), limit=900, tool="search_files")


def test_cap_each_keeps_a_share_of_every_file_instead_of_cutting_one_whole():
    files = {"a.py": numbered(2000), "b.py": numbered(2000), "c.py": "tiny\n"}

    capped = ctx.cap_each(files, tool="read_files", limit=12000, floor=1000)

    assert capped["c.py"] == "tiny\n"
    for name in ("a.py", "b.py"):
        assert capped[name].startswith("line 1\n") and capped[name].rstrip().endswith("line 2000")
        assert "omitted (" in capped[name]


def test_cap_each_leaves_other_results_alone():
    assert ctx.cap_each("a string") == "a string"
    assert ctx.cap_each([1, 2]) == [1, 2]
