import importlib
import inspect
import json
import re
import time
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from core.llm import LLMError, chat_stream, OLLAMA_CODE_MODEL
import core.context as context
import core.conversations as conversations
from core.context import cap_each, cap_result, prune_messages
from core.speech_to_text import listen
from config.settings import env_int
from config.system_prompt import SYSTEM_PROMPT
from core.logger import log_event
from core.permission import ask_cli, needs_approval
from core.runs import AgentRun, park
from features.calendar.calendar import calendar_view_for, create_event_from_command, is_calendar_event_list
from tools.registry import TOOLS
from features.audio.player import describe_play_result, parse_play_command, play_audio_file
from tools.files import parse_script_refactor_command

# 🔁 Agent Flow
# 1. User input
# 2. Try to answer directly from the local model (no tools)
# 3. If that's not enough, the LLM picks tools (Ollama's built-in tool calling)
# 4. Permission check - a call that needs approval parks the run (core/runs.py)
#    until the user answers, then exactly that call runs
# 5. Tool executes (errors are handed back to the model to correct)
# 6. Result fed back to LLM
# 7. Repeat until the model answers without calling a tool

LOCAL_ONLY_PROMPT = """
You are a helpful assistant. Try to answer the user's question directly, from your own knowledge, without using any tools or external access.

If you can answer directly, reply {"action": "none", "response": "your answer"}.

If you cannot answer without a tool (web search, reading/writing project files, calendar, notes, saved audio, looking up earlier conversations, etc.), reply {"action": "needs_tools"}.

Earlier messages in this conversation are shown before the question. If the question follows up on earlier work that used tools (for example another change to files edited before), reply {"action": "needs_tools"}.
"""

# Structured output for the local-first check, so the reply is always this JSON
LOCAL_ANSWER_FORMAT = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["none", "needs_tools"]},
        "response": {"type": "string"},
    },
    "required": ["action"],
}

# Load MAX_STEPS from environment variable, default to 8 if not set
MAX_STEPS = env_int('MAX_STEPS', 8)

# Requests that talk about project files can never be answered from memory.
# Asked directly, the local model replies with manual "open the file and copy
# the block" instructions instead of reporting that it needs the tools, so
# these skip the local-first step entirely. Kept narrow on purpose: a bare
# noun ("what is a project manager?") must still reach the light model, so a
# noun only counts after a determiner ("the template") or an action verb
# ("list files").
FILE_TASK_RE = re.compile(
    r"\.(py|html|css|js|json|md|txt|ics|fish|bat|toml|ya?ml)\b"
    r"|\b(this|the|my|our|your|that|which|any|all)\s+"
    r"(project(?!\s+(manager|management|plan|team|lead|charter))|codebase|repo|repository|files?|templates?|folders?|directory)\b"
    r"|\b(list|show|read|open|edit|find|search|delete|rename|move|create|write|fix|update)\s+(\w+\s+)?"
    r"(files?|folders?|directory|directories|templates?|codebase|repo|repository)\b",
    re.I,
)

# Questions about the code itself that name no file: a constant or function
# ("MAX_STEPS", "run_agent", "needs_tools()") or "where is X defined/used".
# Case-sensitive on purpose - the identifier shapes are what is being matched.
CODE_QUESTION_RE = re.compile(
    r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b"
    r"|\b[a-z][a-z0-9]*_[a-z0-9_]+\b"
    r"|\b\w+\(\)"
    r"|\b[Ww]here\s+(?:is|are|does|do)\b.*\b(defined|declared|implemented|configured|loaded)\b"
)

# External tools the user approved in this CLI process (the web keeps its own
# per login session, see core/agent_routes.py)
_cli_granted = set()


def needs_tools(user_input):
    return bool(user_input and (FILE_TASK_RE.search(user_input) or CODE_QUESTION_RE.search(user_input)))


def parse_decision(raw):
    """Parse a JSON decision out of model text. Returns a dict, or None if there is none.

    Small models wrap the object in markdown fences or an apology, so the JSON
    is dug out of the surrounding text rather than treated as a failure.
    """
    if not raw:
        return None

    text = str(raw).strip()

    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.lower().startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break

    try:
        decision = json.loads(text)
    except Exception:
        # Fall back to the outermost {...} span
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            decision = json.loads(text[start:end + 1])
        except Exception:
            return None

    return decision if isinstance(decision, dict) else None


def planned_first_decision(user_input):
    """Force the right first tool for intents the local model gets wrong.

    Returned as a normal tool call, so it still goes through the permission
    gate and the result is still fed back into the loop.
    """
    script_args = parse_script_refactor_command(user_input)
    if script_args is not None:
        return {
            "name": "extract_inline_scripts",
            "arguments": script_args,
            "reason": "Move the inline script out to its own file and link it",
        }

    return None


def decision_args(decision):
    """The argument dict, under whichever key the model happened to use."""
    for key in ("arguments", "args", "parameters", "params", "input"):
        value = decision.get(key)
        if isinstance(value, dict):
            return value

    return {}


def _tool_func(action):
    module_path, func_name = TOOLS[action]["func"].rsplit(".", 1)
    return getattr(importlib.import_module(module_path), func_name)


def execute_tool(action, args):
    return _tool_func(action)(**args)


def tool_schemas():
    """TOOLS in the shape Ollama's built-in tool calling expects."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": tool["description"],
                "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
            },
        }
        for name, tool in TOOLS.items()
    ]


def system_message():
    return {"role": "system", "content": f"{SYSTEM_PROMPT}\nCurrent date and time: {datetime.now():%A %Y-%m-%d %H:%M}\n"}


_RESPONSE_FIELD_RE = re.compile(r'"response"\s*:\s*"((?:[^"\\]|\\.)*)')


def _response_so_far(raw):
    """The text of the "response" field in a (possibly unfinished) JSON reply, with escapes decoded."""
    match = _RESPONSE_FIELD_RE.search(raw)
    if not match:
        return ""
    text = match.group(1)
    if (len(text) - len(text.rstrip("\\"))) % 2:  # a half-received escape at the end
        text = text[:-1]
    try:
        return json.loads(f'"{text}"')
    except ValueError:
        return text


def _stream_local_answer(messages):
    """chat_stream for the structured local-first reply, showing only the answer as it is written.

    The raw stream is JSON ({"action": ..., "response": ...}); passing that on
    put the protocol into the web UI's live text. Thinking passes through, the
    content becomes just the growing "response" text, and nothing at all is
    shown when the model asks for tools. Returns the full assistant message.
    """
    stream = chat_stream(messages, format=LOCAL_ANSWER_FORMAT)
    raw, shown = "", ""
    try:
        while True:
            event = next(stream)
            if event.get("event") != "llm_delta" or event.get("kind") != "content":
                yield event
                continue
            raw += event.get("text", "")
            answer = _response_so_far(raw)
            if len(answer) > len(shown) and answer.startswith(shown):
                yield {**event, "text": answer[len(shown):]}
                shown = answer
    except StopIteration as done:
        return done.value


def try_local_answer(user_input, history=()):
    """Ask the local model to answer directly, without any tools.

    history is the conversation's earlier turns (core.conversations.history_messages).
    A generator (llm_delta events while the model writes) - use
    `answer = yield from try_local_answer(...)`. Returns the answer text, or
    None if the model needs a tool to proceed.
    """
    message = yield from _stream_local_answer(
        [{"role": "system", "content": LOCAL_ONLY_PROMPT}, *history, {"role": "user", "content": user_input}]
    )
    raw = message.get("content") or ""
    log_event({"type": "llm_raw_decision", "raw": raw, "mode": "local_first"})

    decision = parse_decision(raw)
    if decision is None:
        # Asked for JSON and didn't give it - in practice the model got
        # confused or refused ("I can't interact with your calendar") rather
        # than gave a real answer, so treat it as needing a tool.
        return None

    if decision.get("action") in (None, "none") and decision.get("response"):
        return decision["response"]

    return None


def _normalize_args(args):
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return {}
    return args if isinstance(args, dict) else {}


# qwen3-coder's own tool-call syntax. Ollama normally turns it into
# tool_calls, but when the model writes text before the call the parse can
# fail and the raw markup lands in content instead.
XML_CALL_RE = re.compile(r"<function=([\w.-]+)>(.*?)(?:</function>|$)", re.S)
XML_PARAM_RE = re.compile(r"<parameter=([\w.-]+)>\n?(.*?)\n?</parameter>", re.S)


def _xml_param_value(tool_name, key, text):
    """Values arrive as text; decode JSON (numbers, lists, booleans) unless the schema says string."""
    schema = ((TOOLS.get(tool_name) or {}).get("parameters") or {}).get("properties", {}).get(key, {})
    if schema.get("type", "string") == "string":
        return text
    try:
        return json.loads(text)
    except ValueError:
        return text


def _xml_tool_calls(content):
    calls = []
    for name, body in XML_CALL_RE.findall(content):
        args = {key: _xml_param_value(name, key, value) for key, value in XML_PARAM_RE.findall(body)}
        calls.append({"name": name, "arguments": args})
    return calls


def _calls_from_message(message):
    """The tool calls in an assistant message, as [{"name", "arguments", "reason"}]."""
    content = message.get("content") or ""
    reason = content.split("<function=", 1)[0].replace("<tool_call>", "").strip() or None
    calls = [
        {"name": (call.get("function") or {}).get("name"),
         "arguments": _normalize_args((call.get("function") or {}).get("arguments")),
         "reason": reason}
        for call in message.get("tool_calls") or []
    ]
    if calls:
        return calls

    calls = [dict(call, reason=reason) for call in _xml_tool_calls(content)]
    if calls:
        return calls

    # Some models still write the call as JSON text instead of using the
    # tool-calling API - accept it when it names a real tool.
    decision = parse_decision(content)
    action = decision.get("action") or decision.get("name") if decision else None
    if isinstance(action, str) and action in TOOLS:
        return [{"name": action, "arguments": decision_args(decision), "reason": decision.get("reason")}]

    return []


def _final_text(message):
    # qwen3-coder sometimes leaves a dangling <tool_call> tag after its answer
    content = re.sub(r"</?tool_call>", "", message.get("content") or "").strip()
    decision = parse_decision(content) if content.startswith(("{", "```")) else None
    if decision and decision.get("action") == "none" and decision.get("response"):
        return decision["response"]
    return content or "The model returned an empty answer."


def _signature(name, args):
    return f"{name}:{json.dumps(args, sort_keys=True, default=str)}"


def _tool_result(run, name, text):
    run.messages.append({"role": "tool", "tool_name": str(name), "content": cap_result(text, tool=name)})


def _result_text(result):
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except Exception:
        return str(result)


# Arguments that say what a call was about, for the conversation history -
# never file contents or replacement text.
_SUMMARY_ARGS = ("path", "paths", "dest", "keyword", "query", "title", "start", "country", "urls", "number")


# Tools report most failures as plain text rather than raising, so a call that
# "worked" may only have returned one of these. The turn history must not claim
# an edit that never happened.
_FAILURE_PREFIXES = (
    "ERROR", "Access denied", "File not found", "No path provided", "No content provided",
    "No old_text provided", "No search term provided", "No files matched", "No lines ",
    "No inline", "old_text ", "Rate limit", "urls must", "Unknown", "Could not",
)


def _reported_failure(result):
    return isinstance(result, str) and result.lstrip().startswith(_FAILURE_PREFIXES)


def _action_summary(name, args):
    parts = []
    for key in _SUMMARY_ARGS:
        value = args.get(key) if isinstance(args, dict) else None
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            value = ", ".join(map(str, value))
        parts.append(str(value) if key in ("path", "paths") else f"{key}={value}")
    return " ".join([name, *parts])[:200]


def _assistant_message(content, calls):
    return {
        "role": "assistant",
        "content": content or "",
        "tool_calls": [{"function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls],
    }


def _run_call(run, call, approved):
    """Run (or record the denial of) one tool call. Returns True if the run is finished."""
    name, args = call["name"], call["arguments"]
    tool = TOOLS[name]
    run.attempted.add(_signature(name, args))

    if not approved:
        log_event({"type": "permission_denied", "action": name, "args": args})
        _tool_result(run, name, (
            "ERROR: the user denied permission for this call. Do not try it again. "
            "Finish with an answer that says what you could not do."
        ))
        yield {"event": "status", "message": f"Permission denied for {name}, letting the model finish..."}
        return False

    yield {"event": "status", "message": f"Executing tool: {name}"}
    started = time.perf_counter()
    try:
        result = execute_tool(name, args)
    except Exception as e:
        try:
            expected = str(inspect.signature(_tool_func(name)))
        except Exception:
            expected = "see the tool description"
        log_event({"type": "tool_error", "step": run.step, "action": name, "args": args, "error": repr(e)})
        _tool_result(run, name, f"ERROR {type(e).__name__}: {e}. {name} takes {expected}.")
        yield {"event": "status", "message": f"Tool {name} failed ({type(e).__name__}), letting the model correct it..."}
        return False

    summary = _action_summary(name, args)
    run.actions.append(f"{summary} (failed)" if _reported_failure(result) else summary)

    # A change can make an earlier identical call (verify_app, read_files)
    # worth running again, so the repeat guard starts over.
    if tool.get("risk") == "high":
        run.attempted.clear()

    # A newly created event is shown in the calendar with the final answer
    if name == "create_calendar_event" and args.get("start"):
        run.show_calendar = calendar_view_for(args["start"])

    tool_seconds = time.perf_counter() - started
    # Several files in one read: cap each separately so none loses all of its content
    result_text = _result_text(cap_each(result, tool=name))
    log_event({
        "type": "tool_execution",
        "seconds": round(tool_seconds, 2),
        "step": run.step,
        "action": name,
        "args": args,
        "result": result_text[:500]
    })

    yield {"event": "status", "message": f"Tool {name} completed in {tool_seconds:.1f}s."}

    # A calendar event list is shown as the month-grid calendar, not fed
    # back to the LLM for a text summary.
    if is_calendar_event_list(result):
        first = result[0]
        yield {
            "event": "final_response",
            "response": "",
            "show_calendar": {"year": first["date"].year, "month": first["date"].month},
        }
        return True

    _tool_result(run, name, result_text)
    return False


def _handle_call(run, call, interactive):
    """Check, approve and run one queued call. Returns "continue", "paused" or "finished"."""
    name, args = call["name"], call["arguments"]
    tool = TOOLS.get(name) if isinstance(name, str) else None

    if tool is None:
        # Hallucinated tool - correct it instead of giving up
        if run.unknown_tool_retries > 0:
            run.unknown_tool_retries -= 1
            _tool_result(run, name, f"ERROR: there is no tool called '{name}'. Use one of: {', '.join(TOOLS)}.")
            yield {"event": "status", "message": f"No such tool '{name}', retrying..."}
            return "continue"

        yield {"event": "error", "message": f"Unknown action: {name}"}
        return "finished"

    # Small models get stuck repeating the same call - tell them instead of re-running it
    if _signature(name, args) in run.attempted:
        _tool_result(run, name, (
            "You already made this exact call - its result is above. Do not repeat it. "
            "Choose a different action, or give your final answer."
        ))
        return "continue"

    approved = True
    if needs_approval(name, tool, run.granted):
        if not interactive:
            run.pending = call
            run_id = park(run)
            yield {
                "event": "permission_required",
                "run_id": run_id,
                "action": name,
                "args": args,
                "risk": tool["risk"],
                "external": bool(tool.get("external")),
                "reason": call.get("reason"),
            }
            return "paused"

        yield {"event": "status", "message": f"Requesting permission for tool: {name}"}
        approved = ask_cli(name, args, tool["risk"], reason=call.get("reason"))
        if approved and tool.get("external"):
            run.granted.add(name)

    finished = yield from _run_call(run, call, approved)
    return "finished" if finished else "continue"


def _loop(run, interactive, approved=None):
    """The tool loop. Picks up a parked run's pending call first, if there is one."""
    if run.pending is not None:
        call, run.pending = run.pending, None
        if approved and TOOLS[call["name"]].get("external"):
            run.granted.add(call["name"])
        finished = yield from _run_call(run, call, approved)
        if finished:
            return

    while True:
        while run.queue:
            outcome = yield from _handle_call(run, run.queue.pop(0), interactive)
            if outcome != "continue":
                return

        if run.step >= MAX_STEPS:
            yield {"event": "final_response", "response": "Max steps reached without conclusion."}
            return

        run.step += 1
        yield {"event": "status", "message": f"Step {run.step}: asking the LLM for next action..."}
        history = prune_messages(run.messages)
        if history is not run.messages:
            # Stubbed results tell the model to call the tool again for the
            # exact text - the repeat guard must not refuse that.
            run.attempted.clear()
        started = time.perf_counter()
        try:
            message = yield from chat_stream(history, model=OLLAMA_CODE_MODEL, tools=tool_schemas())
        except LLMError as e:
            yield {"event": "error", "message": str(e)}
            return

        llm_seconds = time.perf_counter() - started
        tokens_in = context.estimate_tokens(history)
        log_event({"type": "llm_raw_decision", "raw": message.get("content"), "tool_calls": message.get("tool_calls")})
        log_event({"type": "step_timing", "step": run.step, "llm_seconds": round(llm_seconds, 2), "est_tokens_in": tokens_in})
        yield {"event": "status", "message": f"LLM decision complete in {llm_seconds:.1f}s (~{tokens_in:,} tokens in)."}

        calls = _calls_from_message(message)
        if not calls:
            final = {"event": "final_response", "response": _final_text(message)}
            if run.show_calendar:
                final["show_calendar"] = run.show_calendar
            yield final
            return

        yield {"event": "status", "message": f"LLM chose action: {', '.join(str(c['name']) for c in calls)}"}
        # Keep the model's own text only when the calls came through the API;
        # a call written into the text would otherwise appear twice.
        native = bool(message.get("tool_calls"))
        run.messages.append(_assistant_message(message.get("content") if native else calls[0]["reason"], calls))
        run.queue = calls


def _run_steps(run, interactive):
    """Shortcuts, the local-first answer, then the tool loop. Shared by run_agent and stream_agent.

    Yields status/error/final_response/permission_required events. A
    permission_required event is only produced when not interactive (the web
    flow) - interactively (the CLI) approval is asked on the terminal instead.
    """
    user_input = run.user_input

    # Bypass the LLM for calendar-creation commands - the local model isn't
    # reliable at recognizing this needs the calendar tool rather than
    # answering "I can't do that" directly.
    calendar_result = create_event_from_command(user_input)
    if calendar_result is not None:
        yield {"event": "final_response", **calendar_result}
        return

    # Bypass the LLM for "play ..." requests - same reasoning as the calendar
    # bypass above. The result also carries structured "audio" data the web
    # UI needs (which file to load, or which candidates to offer); the CLI
    # just ignores that part and prints the text.
    play_args = parse_play_command(user_input)
    if play_args is not None:
        result = play_audio_file(**play_args)
        yield {"event": "final_response", "response": describe_play_result(result), "audio": result}
        return

    if needs_tools(user_input):
        yield {"event": "status", "message": "This needs the project tools, skipping the local model..."}
    else:
        yield {"event": "status", "message": "Trying local model..."}

        try:
            local_answer = yield from try_local_answer(user_input, run.history)
        except LLMError as e:
            yield {"event": "error", "message": str(e)}
            return

        if local_answer is not None:
            yield {"event": "final_response", "response": local_answer}
            return

        yield {"event": "status", "message": "Local model needs tools, continuing..."}

    run.messages = [system_message(), *run.history, {"role": "user", "content": user_input}]

    planned = planned_first_decision(user_input)
    if planned is not None:
        run.messages.append(_assistant_message("", [planned]))
        run.queue = [planned]

    yield from _loop(run, interactive)


def run_agent(user_input):
    """CLI/synchronous entry point. Drains _run_steps and returns the final text.

    Approvals are asked on the terminal; external tools approved once stay
    approved for the rest of the CLI session.
    """
    log_event({"type": "user_input", "input": user_input})
    print(f"Input: {user_input}")

    final_response = "Max steps reached without conclusion."
    run = _new_run(user_input, cli_conversation_id(), granted=_cli_granted)

    for event in _recorded(run, _run_steps(run, interactive=True)):
        etype = event.get("event")

        if etype == "status":
            print(event["message"])
        elif etype in ("final_response", "error"):
            final_response = event.get("response", event.get("message"))
            # A calendar view with no text (an LLM-chosen read_calendar) goes
            # to the caller as the month to open; text is printed as is.
            if event.get("show_calendar") and not final_response:
                final_response = {"show_calendar": event["show_calendar"]}

    return final_response


def stream_agent(user_input, owner=None, granted=(), conversation_id=None):
    """Web entry point. Yields status/llm_delta/final_response/error/permission_required events.

    owner is the login session id (only it can resume a parked run); granted
    is the external tools that session already approved; conversation_id is
    the session's conversation (core/conversations.py) - its earlier turns
    are sent with the question, and this one is stored when it finishes.
    """
    log_event({"type": "user_input", "input": user_input, "stream": True})
    run = _new_run(user_input, conversation_id, owner=owner, granted=set(granted))
    yield from _recorded(run, _run_steps(run, interactive=False))


def resume_agent(run, approved):
    """Continue a parked run (core.runs.take) with the user's answer for its pending call."""
    log_event({"type": "permission_decision", "action": run.pending and run.pending["name"], "approved": approved})
    yield from _recorded(run, _loop(run, interactive=False, approved=approved))


def _new_run(user_input, conversation_id, **kwargs):
    history = conversations.history_messages(conversation_id)
    return AgentRun(user_input, conversation_id=conversation_id, history=history, **kwargs)


def _recorded(run, events):
    return conversations.record(events, run.conversation_id, run.user_input, run.actions)


# The CLI's conversation: one per process, until "/new"
_cli_conversation = None


def cli_conversation_id(new=False):
    global _cli_conversation
    if new or _cli_conversation is None:
        _cli_conversation = conversations.new_conversation()
    return _cli_conversation


if __name__ == "__main__":
    mode = input("Type (t) or Speak (s)? ").strip().lower()

    while True:

        if mode == "s":
            input("🎤 Press ENTER when ready to speak...")
            user_input = listen()
        else:
            user_input = input(">> ")

        if user_input.lower() in ["switch input mode"]:
            mode = input("Switch to Type (t) or Speak (s)? ").strip().lower()
            continue

        if user_input.lower() in ["switch to speech"]:
            mode = "s"
            continue

        if user_input.lower() in ["switch to text"]:
            mode = "t"
            continue

        if user_input.strip().lower() in ["/new", "new chat", "new conversation"]:
            cli_conversation_id(new=True)
            print("Started a new conversation.")
            continue

        if user_input.lower() in ["exit", "quit"]:
            print("Exiting agent.")
            break

        print(run_agent(user_input))
